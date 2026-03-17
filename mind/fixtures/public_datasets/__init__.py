"""Public dataset fixture adapters and compilation helpers."""

from .compiler import (
    build_long_horizon_manifest,
    compile_answer_cases,
    compile_long_horizon_sequences,
    compile_objects,
    compile_retrieval_cases,
)
from .contracts import (
    NormalizedAnswerSpec,
    NormalizedEpisodeBundle,
    NormalizedLongHorizonSequenceSpec,
    NormalizedLongHorizonStepSpec,
    NormalizedRetrievalSpec,
    PublicDatasetDescriptor,
    PublicDatasetFixture,
    PublicDatasetOutput,
)
from .evaluation import (
    PublicDatasetEvaluationReport,
    PublicDatasetLongHorizonSummary,
    PublicDatasetWorkspaceSummary,
    evaluate_public_dataset,
    write_public_dataset_evaluation_report_json,
)
from .registry import (
    PublicDatasetAdapter,
    UnknownPublicDatasetError,
    build_public_dataset_answer_cases,
    build_public_dataset_fixture,
    build_public_dataset_long_horizon_manifest,
    build_public_dataset_long_horizon_sequences,
    build_public_dataset_objects,
    build_public_dataset_retrieval_cases,
    get_public_dataset_adapter,
    list_public_dataset_descriptors,
)
from .source_loader import load_public_dataset_fixture_from_path

__all__ = [
    "NormalizedAnswerSpec",
    "NormalizedEpisodeBundle",
    "NormalizedLongHorizonSequenceSpec",
    "NormalizedLongHorizonStepSpec",
    "NormalizedRetrievalSpec",
    "PublicDatasetAdapter",
    "PublicDatasetDescriptor",
    "PublicDatasetEvaluationReport",
    "PublicDatasetFixture",
    "PublicDatasetLongHorizonSummary",
    "PublicDatasetOutput",
    "PublicDatasetWorkspaceSummary",
    "UnknownPublicDatasetError",
    "build_long_horizon_manifest",
    "build_public_dataset_answer_cases",
    "build_public_dataset_fixture",
    "build_public_dataset_long_horizon_manifest",
    "build_public_dataset_long_horizon_sequences",
    "build_public_dataset_objects",
    "build_public_dataset_retrieval_cases",
    "compile_answer_cases",
    "compile_long_horizon_sequences",
    "compile_objects",
    "compile_retrieval_cases",
    "evaluate_public_dataset",
    "get_public_dataset_adapter",
    "list_public_dataset_descriptors",
    "load_public_dataset_fixture_from_path",
    "write_public_dataset_evaluation_report_json",
]
