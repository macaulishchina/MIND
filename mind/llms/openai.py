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
    """

    def __init__(self, config: LLMConfig, **kwargs) -> None:
        self.config = config
        sdk_base = config.base_url.rstrip("/") + config.sdk_base
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=sdk_base,
        )

    def _generate(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
