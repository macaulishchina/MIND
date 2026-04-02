"""OpenAI-protocol LLM implementation."""

import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI

from mind.config.schema import LLMConfig
from mind.llms.base import BaseLLM

logger = logging.getLogger(__name__)


class OpenAILLM(BaseLLM):
    """OpenAI-protocol LLM.

    The OpenAI SDK internally appends ``/chat/completions``,
    so we pass ``base_url = base + sdk_base`` (from protocol config).

    When ``config.batch`` is *True* and ``config.batch_base_url`` is
    non-empty, the client is pointed at the batch endpoint and the SDK
    timeout is extended to ``config.batch_timeout`` (default 3600 s)
    so that queued Batch Chat requests are not prematurely aborted.
    """

    def __init__(self, config: LLMConfig, **kwargs) -> None:
        self.config = config

        use_batch = config.batch and bool(config.batch_base_url)
        if config.batch and not config.batch_base_url:
            logger.warning(
                "batch=True but batch_base_url is empty for provider '%s' "
                "— falling back to normal endpoint",
                config.provider,
            )

        if use_batch:
            base = config.batch_base_url.rstrip("/") + config.sdk_base
            self.client = OpenAI(
                api_key=config.api_key,
                base_url=base,
                timeout=config.batch_timeout,
            )
            logger.info(
                "OpenAILLM: batch mode ON — base_url=%s, timeout=%.0fs",
                base, config.batch_timeout,
            )
        else:
            sdk_base = config.base_url.rstrip("/") + config.sdk_base
            self.client = OpenAI(
                api_key=config.api_key,
                base_url=sdk_base,
                timeout=config.timeout,
            )

    def _generate(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": (
                self.config.temperature if temperature is None else temperature
            ),
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
