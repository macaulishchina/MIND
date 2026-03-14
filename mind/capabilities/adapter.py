"""Adapter protocol and validation helpers for capability calls."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from .contracts import (
    CAPABILITY_CATALOG,
    CapabilityModel,
    CapabilityName,
    CapabilityProviderFamily,
    CapabilityRequest,
    CapabilityResponse,
    response_model_for,
)


class CapabilityAdapterError(RuntimeError):
    """Raised when a capability adapter violates the frozen contract."""


class CapabilityAdapterDescriptor(CapabilityModel):
    """Frozen identity and support metadata for one adapter."""

    adapter_name: str = Field(min_length=1)
    provider_family: CapabilityProviderFamily
    model: str = Field(min_length=1)
    version: str = Field(min_length=1)
    api_style: str = Field(min_length=1)
    supported_capabilities: list[CapabilityName] = Field(min_length=1)


@runtime_checkable
class CapabilityAdapter(Protocol):
    """Single dispatch surface used by the Phase K capability layer."""

    descriptor: CapabilityAdapterDescriptor

    def invoke(self, request: CapabilityRequest) -> CapabilityResponse:
        """Execute one capability request."""


def validate_capability_response(
    request: CapabilityRequest,
    response: CapabilityResponse,
) -> CapabilityResponse:
    """Ensure the adapter returned the right response contract."""

    expected_model = response_model_for(request.capability)
    if not isinstance(response, expected_model):
        raise CapabilityAdapterError(
            "adapter returned unexpected response model "
            f"for capability {request.capability.value}: {type(response).__name__}"
        )
    if response.capability is not request.capability:
        raise CapabilityAdapterError(
            "adapter returned mismatched capability "
            f"{response.capability.value} for request {request.capability.value}"
        )
    return response


def supports_capability(adapter: CapabilityAdapter, capability: CapabilityName) -> bool:
    """Return whether an adapter declares support for one capability."""

    return capability in adapter.descriptor.supported_capabilities


def invoke_capability(
    adapter: CapabilityAdapter,
    request: CapabilityRequest,
) -> CapabilityResponse:
    """Invoke one request and validate the adapter contract."""

    if request.capability not in CAPABILITY_CATALOG:
        raise CapabilityAdapterError(f"unsupported capability {request.capability!r}")
    if not supports_capability(adapter, request.capability):
        raise CapabilityAdapterError(
            f"adapter {adapter.descriptor.adapter_name} does not support {request.capability.value}"
        )
    return validate_capability_response(request, adapter.invoke(request))
