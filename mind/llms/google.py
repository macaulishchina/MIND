"""Google (Gemini) LLM implementation."""

import logging
from typing import Any, Dict, List, Optional

import httpx

from mind.config.schema import LLMConfig
from mind.llms.base import BaseLLM

logger = logging.getLogger(__name__)


class GoogleLLM(BaseLLM):
    """Google Gemini LLM via generateContent REST API (raw HTTP, no SDK)."""

    def __init__(self, config: LLMConfig, **kwargs) -> None:
        self.config = config
        suffix = config.llm_suffix
        if "{model}" in suffix:
            suffix = suffix.replace("{model}", config.model)
        self.url = config.base_url.rstrip("/") + suffix
        self.api_key = config.api_key

    def _generate(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        system_text = ""
        contents: List[Dict[str, Any]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"] + "\n"
            else:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": self.config.temperature},
        }
        if system_text.strip():
            body["systemInstruction"] = {"parts": [{"text": system_text.strip()}]}
        if response_format and response_format.get("type") == "json_object":
            body["generationConfig"]["responseMimeType"] = "application/json"

        response = httpx.post(
            self.url, params={"key": self.api_key}, json=body,
            headers={"content-type": "application/json"}, timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)