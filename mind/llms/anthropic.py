"""Anthropic LLM implementation."""

import logging
from typing import Any, Dict, List, Optional

import httpx

from mind.config.schema import LLMConfig
from mind.llms.base import BaseLLM

logger = logging.getLogger(__name__)
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicLLM(BaseLLM):
    """Anthropic LLM via the Messages API (raw HTTP, no SDK dependency)."""

    def __init__(self, config: LLMConfig, **kwargs) -> None:
        self.config = config
        self.url = config.base_url.rstrip("/") + config.llm_suffix
        self.headers = {
            "x-api-key": config.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _generate(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        system_text = ""
        conversation: List[Dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"] + "\n"
            else:
                conversation.append({"role": msg["role"], "content": msg["content"]})

        body: Dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": 4096,
            "temperature": self.config.temperature,
            "messages": conversation,
        }
        if system_text.strip():
            body["system"] = system_text.strip()
        if response_format and response_format.get("type") == "json_object":
            body["system"] = (body.get("system", "") +
                              "\n\nIMPORTANT: Respond with valid JSON only, "
                              "no markdown fences, no extra text.").strip()

        response = httpx.post(self.url, headers=self.headers, json=body, timeout=120.0)
        response.raise_for_status()
        data = response.json()

        content_blocks = data.get("content", [])
        return "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")