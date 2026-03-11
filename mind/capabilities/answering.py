"""Shared answer-generation helper routed through the capability layer."""

from __future__ import annotations

import hashlib
from functools import lru_cache

from .config import CapabilityAuthConfig, CapabilityProviderConfig
from .contracts import AnswerRequest, CapabilityProviderFamily
from .service import CapabilityService


def generate_answer_text(
    *,
    question: str,
    context_text: str,
    support_ids: tuple[str, ...] = (),
    hard_constraints: tuple[str, ...] = (),
    max_answer_tokens: int | None = None,
    capability_service: CapabilityService | None = None,
    request_id_prefix: str = "answer",
) -> str:
    """Generate answer text through the unified capability layer."""

    service = capability_service or _default_answer_capability_service()
    request_suffix = hashlib.sha1(
        f"{question}\n{context_text}\n{','.join(support_ids)}".encode("utf-8")
    ).hexdigest()[:10]
    response = service.answer(
        AnswerRequest(
            request_id=f"{request_id_prefix}-{request_suffix}",
            question=question,
            context_text=context_text,
            support_ids=list(support_ids),
            hard_constraints=list(hard_constraints),
            max_answer_tokens=max_answer_tokens,
        )
    )
    return response.answer_text


@lru_cache(maxsize=1)
def _default_answer_capability_service() -> CapabilityService:
    return CapabilityService(
        provider_config=CapabilityProviderConfig(
            provider="deterministic",
            provider_family=CapabilityProviderFamily.DETERMINISTIC,
            model="deterministic",
            endpoint="local://deterministic",
            api_version="deterministic-v1",
            timeout_ms=30_000,
            retry_policy="default",
            auth=CapabilityAuthConfig(mode="none"),
        )
    )
