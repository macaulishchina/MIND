"""ConfigManager — the central authority for all MIND configuration.

Responsibilities:
1. Load defaults from ``mind.toml``
2. Resolve ``[llm.*]`` provider entries (with template inheritance)
3. Merge ``[llm]`` globals + selected ``[llm.{provider}]`` into LLMConfig
4. Resolve ``[embedding]`` independently
5. Accept runtime overrides and produce a fully-resolved MemoryConfig

Design principles:
- No environment variables — everything from TOML + programmatic overrides
- Provider definitions live in TOML, not hardcoded
- ``template`` field enables DRY config for third-party providers
"""

import copy
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    import tomllib                       # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib              # fallback for 3.10

from mind.config.schema import (
    EmbeddingConfig,
    HistoryStoreConfig,
    LLMConfig,
    LoggingConfig,
    MemoryConfig,
    ProviderConfig,
    RetrievalConfig,
    VectorStoreConfig,
)

logger = logging.getLogger(__name__)

_DEFAULT_TOML = Path(__file__).resolve().parent.parent.parent / "mind.toml"
_DEFAULT_TEST_TOML = Path(__file__).resolve().parent.parent.parent / "mindt.toml"


class ConfigManager:
    """Load, merge, and resolve MIND configuration.

    Usage::

        mgr = ConfigManager()                  # load mind.toml
        cfg = mgr.get()                        # fully-resolved config

        # Override at call time
        cfg = mgr.get(overrides={"llm": {"provider": "openai"}})
    """

    def __init__(self, toml_path: Optional[Union[str, Path]] = None) -> None:
        path = Path(toml_path) if toml_path else _DEFAULT_TOML
        if path.exists():
            with open(path, "rb") as f:
                self._raw: Dict[str, Any] = tomllib.load(f)
            logger.info("Loaded config from %s", path)
        else:
            self._raw = {}
            logger.warning("Config file not found: %s — using built-in defaults", path)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigManager":
        """Create a ConfigManager from a raw dict (no TOML file)."""
        instance = cls.__new__(cls)
        instance._raw = copy.deepcopy(data)
        return instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, overrides: Optional[Dict[str, Any]] = None) -> MemoryConfig:
        """Produce a fully-resolved MemoryConfig."""
        merged = copy.deepcopy(self._raw)
        if overrides:
            _deep_merge(merged, overrides)
        return self._resolve(merged)

    # ------------------------------------------------------------------
    # Resolution pipeline
    # ------------------------------------------------------------------

    def _resolve(self, raw: Dict[str, Any]) -> MemoryConfig:
        llm_section = raw.get("llm", {})

        # 1. Extract [llm.*] provider sub-tables
        #    TOML nested tables [llm.openai] appear as sub-dicts of llm
        provider_defs: Dict[str, Dict[str, Any]] = {}
        llm_globals: Dict[str, Any] = {}
        for key, value in llm_section.items():
            if isinstance(value, dict):
                provider_defs[key] = value
            else:
                llm_globals[key] = value

        # 2. Resolve template inheritance for each provider
        resolved_providers: Dict[str, Dict[str, Any]] = {}
        for name, pdef in provider_defs.items():
            resolved_providers[name] = self._resolve_template(
                name, pdef, provider_defs
            )

        # 3. Build ProviderConfig objects
        providers: Dict[str, ProviderConfig] = {}
        for name, pdata in resolved_providers.items():
            providers[name] = ProviderConfig(**{
                k: v for k, v in pdata.items()
                if k in ProviderConfig.model_fields
            })

        # 4. Resolve LLM: merge globals + selected provider
        selected = llm_globals.get("provider", "openai")
        provider_cfg = resolved_providers.get(selected, {})

        llm_cfg = LLMConfig(
            provider=selected,
            protocols=provider_cfg.get("protocols", "openai"),
            model=provider_cfg.get("model", ""),
            temperature=llm_globals.get("temperature", 0.0),
            api_key=provider_cfg.get("api_key", ""),
            base_url=provider_cfg.get("base_url", ""),
            sdk_base=provider_cfg.get("sdk_base", ""),
            llm_suffix=provider_cfg.get("llm_suffix", ""),
        )

        # 5. Resolve Embedding (fully independent)
        emb_raw = raw.get("embedding", {})
        emb_cfg = EmbeddingConfig(**{
            k: v for k, v in emb_raw.items()
            if k in EmbeddingConfig.model_fields
        })

        # 6. Other sections
        vs_raw = raw.get("vector_store", {})
        vs_cfg = VectorStoreConfig(**{
            k: v for k, v in vs_raw.items()
            if k in VectorStoreConfig.model_fields
        })

        hs_raw = raw.get("history_store", {})
        hs_cfg = HistoryStoreConfig(**{
            k: v for k, v in hs_raw.items()
            if k in HistoryStoreConfig.model_fields
        })

        ret_raw = raw.get("retrieval", {})
        ret_cfg = RetrievalConfig(**{
            k: v for k, v in ret_raw.items()
            if k in RetrievalConfig.model_fields
        })

        log_raw = raw.get("logging", {})
        log_cfg = LoggingConfig(**{
            k: v for k, v in log_raw.items()
            if k in LoggingConfig.model_fields
        })

        config = MemoryConfig(
            llm=llm_cfg,
            embedding=emb_cfg,
            vector_store=vs_cfg,
            history_store=hs_cfg,
            retrieval=ret_cfg,
            logging=log_cfg,
            providers=providers,
        )

        logger.debug(
            "Resolved: llm=%s (protocols=%s, model=%s), embedding=%s",
            config.llm.provider, config.llm.protocols,
            config.llm.model, config.embedding.model,
        )
        return config

    # ------------------------------------------------------------------
    # Template inheritance
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_template(
        name: str,
        pdef: Dict[str, Any],
        all_providers: Dict[str, Dict[str, Any]],
        _seen: Optional[set] = None,
    ) -> Dict[str, Any]:
        """Resolve ``template`` inheritance, producing a flat dict.

        Example: if deepseek has ``template = "llm.openai"``, we take
        openai's values as base, then overlay deepseek's own values.
        """
        if _seen is None:
            _seen = set()
        if name in _seen:
            raise ValueError(f"Circular template reference detected: {name}")
        _seen.add(name)

        template_ref = pdef.get("template", "")
        if not template_ref:
            return copy.deepcopy(pdef)

        # "llm.openai" → "openai"
        parent_name = template_ref
        if parent_name.startswith("llm."):
            parent_name = parent_name[4:]

        parent_def = all_providers.get(parent_name)
        if parent_def is None:
            raise ValueError(
                f"Provider '{name}' references template '{template_ref}' "
                f"which does not exist"
            )

        # Recursively resolve parent first
        base = ConfigManager._resolve_template(
            parent_name, parent_def, all_providers, _seen
        )

        # Overlay child values (skip empty strings — they mean "inherit")
        for key, value in pdef.items():
            if key == "template":
                continue
            if isinstance(value, str) and value == "":
                continue
            base[key] = value

        return base



# ======================================================================
# Helpers
# ======================================================================

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """Recursively merge *override* into *base* in-place."""
    for key, value in override.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            _deep_merge(base[key], value)
        else:
            base[key] = value