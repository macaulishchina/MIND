"""OpenAI response payload parsing and coercion helpers."""

from __future__ import annotations

import json
from typing import Any

from .adapter import CapabilityAdapterError
from .contracts import (
    AnswerRequest,
    CapabilityRequest,
    OfflineReconstructRequest,
    ReflectRequest,
    SummarizeRequest,
)


def coerce_output_payload(
    request: CapabilityRequest,
    output_text: str,
) -> dict[str, Any]:
    for candidate in _iter_json_candidates(output_text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        payload = _payload_from_parsed_json(request, parsed)
        if payload is not None:
            return payload

    decoder = json.JSONDecoder()
    stripped = output_text.strip()
    for index, char in enumerate(stripped):
        if char not in {"{", "[", '"'}:
            continue
        try:
            parsed, _end = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        payload = _payload_from_parsed_json(request, parsed)
        if payload is not None:
            return payload

    payload = _payload_from_plain_text(request, output_text)
    if payload is not None:
        return payload
    raise CapabilityAdapterError("openai response did not contain valid JSON output")


def _iter_json_candidates(output_text: str) -> list[str]:
    stripped = output_text.strip()
    if not stripped:
        return []
    candidates: list[str] = [stripped]
    if "```" in stripped:
        parts = stripped.split("```")
        for index in range(1, len(parts), 2):
            block = parts[index].strip()
            if not block:
                continue
            if "\n" in block:
                first_line, remainder = block.split("\n", 1)
                if first_line.strip().lower() == "json":
                    block = remainder.strip()
            candidates.append(block)
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _payload_from_parsed_json(
    request: CapabilityRequest,
    parsed: Any,
) -> dict[str, Any] | None:
    if isinstance(parsed, dict):
        return _normalize_payload_mapping(request, parsed)
    if isinstance(parsed, str):
        return _payload_from_plain_text(request, parsed)
    return None


def _payload_from_plain_text(
    request: CapabilityRequest,
    output_text: str,
) -> dict[str, Any] | None:
    text = strip_markdown_fence(output_text)
    if not text:
        return None
    if isinstance(request, SummarizeRequest):
        return {"summary_text": text}
    if isinstance(request, ReflectRequest):
        return {"reflection_text": text, "claims": []}
    if isinstance(request, AnswerRequest):
        return {"answer_text": text}
    if isinstance(request, OfflineReconstructRequest):
        return {"reconstruction_text": text}
    return None


def _normalize_payload_mapping(
    request: CapabilityRequest,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if isinstance(request, SummarizeRequest):
        text = _coerce_mapping_text(
            payload,
            (
                "summary_text",
                "summary",
                "answer_text",
                "answer",
                "response",
                "content",
                "output",
                "text",
                "message",
            ),
        )
        return {"summary_text": text} if text else None
    if isinstance(request, ReflectRequest):
        text = _coerce_mapping_text(
            payload,
            (
                "reflection_text",
                "reflection",
                "answer_text",
                "answer",
                "response",
                "content",
                "output",
                "text",
                "message",
            ),
        )
        if not text:
            return None
        claims = payload.get("claims")
        normalized_claims = [str(item) for item in claims] if isinstance(claims, list) else []
        return {"reflection_text": text, "claims": normalized_claims}
    if isinstance(request, AnswerRequest):
        text = _coerce_mapping_text(
            payload,
            ("answer_text", "answer", "response", "content", "output", "text", "message"),
        )
        return {"answer_text": text} if text else None
    if isinstance(request, OfflineReconstructRequest):
        text = _coerce_mapping_text(
            payload,
            (
                "reconstruction_text",
                "reconstruction",
                "answer_text",
                "answer",
                "response",
                "content",
                "output",
                "text",
                "message",
            ),
        )
        return {"reconstruction_text": text} if text else None
    return None


def _coerce_mapping_text(
    payload: dict[str, Any],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        if key not in payload:
            continue
        text = _stringify_field_value(payload[key])
        if text:
            return text
    return None


def _stringify_field_value(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        fragments = [text for item in value for text in [_stringify_field_value(item)] if text]
        if fragments:
            return " ".join(fragments)
        return None
    if isinstance(value, dict):
        for nested_key in ("text", "content", "message", "answer", "output", "response"):
            if nested_key in value:
                nested_text = _stringify_field_value(value[nested_key])
                if nested_text:
                    return nested_text
        return None
    return None


def strip_markdown_fence(output_text: str) -> str:
    stripped = output_text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        parts = stripped.split("```")
        if len(parts) >= 3:
            block = parts[1].strip()
            if "\n" in block:
                first_line, remainder = block.split("\n", 1)
                if first_line.strip().lower() == "json":
                    return remainder.strip()
            return block.strip()
    return stripped
