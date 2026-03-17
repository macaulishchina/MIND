"""Registry for public dataset benchmark adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from mind.fixtures.episode_answer_bench import EpisodeAnswerBenchCase
from mind.fixtures.long_horizon_eval import LongHorizonEvalManifest, LongHorizonEvalSequence
from mind.fixtures.public_datasets.compiler import (
    build_long_horizon_manifest,
    compile_answer_cases,
    compile_long_horizon_sequences,
    compile_objects,
    compile_retrieval_cases,
)
from mind.fixtures.public_datasets.contracts import PublicDatasetDescriptor, PublicDatasetFixture
from mind.fixtures.public_datasets.hotpotqa import HotpotQAPublicDatasetAdapter
from mind.fixtures.public_datasets.locomo import LoCoMoPublicDatasetAdapter
from mind.fixtures.public_datasets.scifact import SciFactPublicDatasetAdapter
from mind.fixtures.public_datasets.source_loader import load_public_dataset_fixture_from_path
from mind.fixtures.retrieval_benchmark import RetrievalBenchmarkCase


class PublicDatasetAdapter(Protocol):
    """Protocol implemented by all public dataset fixture adapters."""

    descriptor: PublicDatasetDescriptor

    def build_fixture(self) -> PublicDatasetFixture:
        """Build the normalized fixture for this public dataset."""


class UnknownPublicDatasetError(ValueError):
    """Raised when a dataset adapter is requested but not registered."""


_ADAPTERS: dict[str, PublicDatasetAdapter] = {
    adapter.descriptor.dataset_name: adapter
    for adapter in (
        LoCoMoPublicDatasetAdapter(),
        HotpotQAPublicDatasetAdapter(),
        SciFactPublicDatasetAdapter(),
    )
}


def list_public_dataset_descriptors() -> tuple[PublicDatasetDescriptor, ...]:
    """Return the descriptors for all registered public datasets."""

    return tuple(adapter.descriptor for _, adapter in sorted(_ADAPTERS.items()))


def get_public_dataset_adapter(dataset_name: str) -> PublicDatasetAdapter:
    """Return the registered adapter for one dataset name."""

    try:
        return _ADAPTERS[dataset_name]
    except KeyError as exc:
        raise UnknownPublicDatasetError(f"unknown public dataset adapter: {dataset_name}") from exc


def build_public_dataset_fixture(
    dataset_name: str,
    source_path: str | Path | None = None,
) -> PublicDatasetFixture:
    """Build the normalized public dataset fixture for one adapter."""

    adapter = get_public_dataset_adapter(dataset_name)
    if source_path is None:
        return adapter.build_fixture()
    return load_public_dataset_fixture_from_path(adapter.descriptor, source_path)


def build_public_dataset_objects(
    dataset_name: str,
    source_path: str | Path | None = None,
) -> list[dict[str, object]]:
    """Build the flattened object corpus for one public dataset adapter."""

    return compile_objects(build_public_dataset_fixture(dataset_name, source_path=source_path))


def build_public_dataset_retrieval_cases(
    dataset_name: str,
    source_path: str | Path | None = None,
) -> list[RetrievalBenchmarkCase]:
    """Build retrieval benchmark cases for one public dataset adapter."""

    return compile_retrieval_cases(
        build_public_dataset_fixture(dataset_name, source_path=source_path)
    )


def build_public_dataset_answer_cases(
    dataset_name: str,
    source_path: str | Path | None = None,
) -> list[EpisodeAnswerBenchCase]:
    """Build answer benchmark cases for one public dataset adapter."""

    return compile_answer_cases(build_public_dataset_fixture(dataset_name, source_path=source_path))


def build_public_dataset_long_horizon_sequences(
    dataset_name: str,
    source_path: str | Path | None = None,
) -> list[LongHorizonEvalSequence]:
    """Build long-horizon benchmark sequences for one public dataset adapter."""

    return compile_long_horizon_sequences(
        build_public_dataset_fixture(dataset_name, source_path=source_path)
    )


def build_public_dataset_long_horizon_manifest(
    dataset_name: str,
    source_path: str | Path | None = None,
) -> LongHorizonEvalManifest:
    """Build the long-horizon manifest for one public dataset adapter."""

    return build_long_horizon_manifest(
        build_public_dataset_fixture(dataset_name, source_path=source_path)
    )
