"""Tests for Batch Chat configuration and OpenAILLM batch routing."""

from __future__ import annotations

import logging
from unittest.mock import patch, MagicMock

from mind.config import ConfigManager
from mind.config.schema import LLMConfig, ProviderConfig


# ── Config resolution tests ──────────────────────────────────────────


def test_batch_defaults_are_false():
    """LLMConfig defaults: batch=False, batch_base_url empty, batch_timeout 3600."""
    cfg = LLMConfig()
    assert cfg.batch is False
    assert cfg.batch_base_url == ""
    assert cfg.batch_timeout == 3600.0


def test_provider_config_has_batch_base_url():
    """ProviderConfig accepts batch_base_url."""
    p = ProviderConfig(batch_base_url="https://batch.example.com")
    assert p.batch_base_url == "https://batch.example.com"


def test_config_resolution_propagates_batch_fields():
    """batch from [llm] globals and batch_base_url from provider are resolved."""
    mgr = ConfigManager.from_dict({
        "llm": {
            "provider": "test",
            "batch": True,
            "batch_timeout": 1800.0,
            "test": {
                "protocols": "openai",
                "api_key": "k",
                "base_url": "https://api.example.com",
                "sdk_base": "/v1",
                "model": "m",
                "batch_base_url": "https://batch.example.com",
            },
        },
    })
    cfg = mgr.get()
    assert cfg.llm.batch is True
    assert cfg.llm.batch_base_url == "https://batch.example.com"
    assert cfg.llm.batch_timeout == 1800.0


def test_config_resolution_batch_disabled_by_default():
    """When [llm] has no batch key, it defaults to False."""
    mgr = ConfigManager.from_dict({
        "llm": {
            "provider": "test",
            "test": {
                "protocols": "openai",
                "api_key": "k",
                "base_url": "https://api.example.com",
                "sdk_base": "/v1",
                "model": "m",
            },
        },
    })
    cfg = mgr.get()
    assert cfg.llm.batch is False
    assert cfg.llm.batch_base_url == ""


def test_template_inheritance_propagates_batch_base_url():
    """batch_base_url defined on parent is inherited by child via template."""
    mgr = ConfigManager.from_dict({
        "llm": {
            "provider": "child",
            "batch": True,
            "child": {
                "template": "llm.parent",
                "api_key": "child-key",
                "model": "child-model",
            },
            "parent": {
                "protocols": "openai",
                "api_key": "parent-key",
                "base_url": "https://api.example.com",
                "sdk_base": "/v1",
                "model": "parent-model",
                "batch_base_url": "https://batch.example.com",
            },
        },
    })
    cfg = mgr.get()
    assert cfg.llm.batch_base_url == "https://batch.example.com"


def test_template_child_overrides_batch_base_url():
    """Child provider can override parent's batch_base_url."""
    mgr = ConfigManager.from_dict({
        "llm": {
            "provider": "child",
            "batch": True,
            "child": {
                "template": "llm.parent",
                "api_key": "k",
                "model": "m",
                "batch_base_url": "https://batch-child.example.com",
            },
            "parent": {
                "protocols": "openai",
                "api_key": "k",
                "base_url": "https://api.example.com",
                "sdk_base": "/v1",
                "model": "m",
                "batch_base_url": "https://batch-parent.example.com",
            },
        },
    })
    cfg = mgr.get()
    assert cfg.llm.batch_base_url == "https://batch-child.example.com"


def test_decision_stage_override_inherits_provider_defaults():
    """Active stage configs resolve on top of [llm] globals and providers."""
    mgr = ConfigManager.from_dict({
        "llm": {
            "provider": "test",
            "temperature": 0.1,
            "test": {
                "protocols": "fake",
                "model": "base-model",
            },
            "alt": {
                "protocols": "fake",
                "model": "alt-model",
            },
            "decision": {
                "provider": "alt",
                "temperature": 0.3,
            },
        },
    })
    cfg = mgr.get()

    assert cfg.llm.model == "base-model"
    assert cfg.llm_stages["decision"].provider == "alt"
    assert cfg.llm_stages["decision"].model == "alt-model"
    assert cfg.llm_stages["decision"].temperature == 0.3


def test_legacy_extraction_and_normalization_stages_are_ignored(caplog):
    """Deprecated extraction/normalization stage overrides are ignored."""
    mgr = ConfigManager.from_dict({
        "llm": {
            "provider": "test",
            "test": {
                "protocols": "fake",
                "model": "base-model",
            },
            "alt": {
                "protocols": "fake",
                "model": "alt-model",
            },
            "extraction": {
                "provider": "alt",
                "temperature": 0.3,
            },
            "normalization": {
                "provider": "alt",
                "temperature": 0.4,
            },
        },
    })

    with caplog.at_level(logging.WARNING, logger="mind.config.manager"):
        cfg = mgr.get()

    assert "extraction" not in cfg.llm_stages
    assert "normalization" not in cfg.llm_stages
    assert "Ignoring deprecated [llm.extraction] override" in caplog.text
    assert "Ignoring deprecated [llm.normalization] override" in caplog.text


def test_stl_extraction_stage_override_is_resolved():
    """stl_extraction participates in stage resolution like other stages."""
    mgr = ConfigManager.from_dict({
        "llm": {
            "provider": "test",
            "temperature": 0.1,
            "test": {
                "protocols": "fake",
                "model": "base-model",
            },
            "alt": {
                "protocols": "fake",
                "model": "alt-model",
            },
            "stl_extraction": {
                "provider": "alt",
                "temperature": 0.2,
            },
        },
    })
    cfg = mgr.get()

    assert cfg.llm_stages["stl_extraction"].provider == "alt"
    assert cfg.llm_stages["stl_extraction"].model == "alt-model"
    assert cfg.llm_stages["stl_extraction"].temperature == 0.2


# ── OpenAILLM routing tests ─────────────────────────────────────────


@patch("mind.llms.openai.OpenAI")
def test_openai_llm_uses_batch_url_when_enabled(mock_openai_cls):
    """With batch=True + batch_base_url, client uses batch endpoint."""
    from mind.llms.openai import OpenAILLM

    cfg = LLMConfig(
        provider="aliyun",
        protocols="openai",
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com",
        sdk_base="/compatible-mode/v1",
        model="deepseek-v3.2",
        batch=True,
        batch_base_url="https://batch.dashscope.aliyuncs.com",
        batch_timeout=3600.0,
    )
    OpenAILLM(cfg)
    mock_openai_cls.assert_called_once_with(
        api_key="test-key",
        base_url="https://batch.dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=3600.0,
    )


@patch("mind.llms.openai.OpenAI")
def test_openai_llm_uses_normal_url_when_batch_disabled(mock_openai_cls):
    """With batch=False, client uses normal endpoint (no timeout override)."""
    from mind.llms.openai import OpenAILLM

    cfg = LLMConfig(
        provider="aliyun",
        protocols="openai",
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com",
        sdk_base="/compatible-mode/v1",
        model="deepseek-v3.2",
        batch=False,
        batch_base_url="https://batch.dashscope.aliyuncs.com",
    )
    OpenAILLM(cfg)
    mock_openai_cls.assert_called_once_with(
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=120.0,
    )


@patch("mind.llms.openai.OpenAI")
def test_openai_llm_fallback_when_batch_url_empty(mock_openai_cls, caplog):
    """batch=True but empty batch_base_url → fallback to normal + warning."""
    from mind.llms.openai import OpenAILLM

    cfg = LLMConfig(
        provider="aliyun",
        protocols="openai",
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com",
        sdk_base="/compatible-mode/v1",
        model="deepseek-v3.2",
        batch=True,
        batch_base_url="",
    )
    with caplog.at_level(logging.WARNING, logger="mind.llms.openai"):
        OpenAILLM(cfg)

    mock_openai_cls.assert_called_once_with(
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=120.0,
    )
    assert "falling back to normal endpoint" in caplog.text


@patch("mind.llms.openai.OpenAI")
def test_openai_llm_custom_batch_timeout(mock_openai_cls):
    """Custom batch_timeout is passed to the SDK."""
    from mind.llms.openai import OpenAILLM

    cfg = LLMConfig(
        provider="aliyun",
        protocols="openai",
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com",
        sdk_base="/compatible-mode/v1",
        model="m",
        batch=True,
        batch_base_url="https://batch.dashscope.aliyuncs.com",
        batch_timeout=1800.0,
    )
    OpenAILLM(cfg)
    mock_openai_cls.assert_called_once_with(
        api_key="test-key",
        base_url="https://batch.dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=1800.0,
    )
