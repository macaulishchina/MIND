"""End-to-end memory lifecycle benchmark helpers."""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from mind.access.contracts import AccessMode, AccessRunResponse
from mind.access.service import AccessService
from mind.capabilities import (
    CapabilityPortAdapter,
    CapabilityService,
    resolve_capability_provider_config,
)
from mind.fixtures.episode_answer_bench import AnswerKind, EpisodeAnswerBenchCase
from mind.kernel.contracts import PrimitiveCostCategory, PrimitiveOutcome, RetrieveQueryMode
from mind.kernel.retrieval import build_query_embedding
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJobKind,
    OfflineMaintenanceService,
    PromoteSchemaJobPayload,
    new_offline_job,
)
from mind.primitives.contracts import PrimitiveExecutionContext
from mind.primitives.service import PrimitiveService
from mind.telemetry import (
    JsonlTelemetryRecorder,
    TelemetryEvent,
    TelemetryEventKind,
    TelemetryScope,
)
from mind.workspace.answer_benchmark import GeneratedAnswer, score_answer


@dataclass(frozen=True)
class MemoryLifecycleAskMetrics:
    """Aggregate ask metrics for one lifecycle stage."""

    answer_case_count: int
    average_answer_quality: float
    task_success_rate: float
    candidate_hit_rate: float
    selected_hit_rate: float
    reuse_rate: float
    pollution_rate: float


@dataclass(frozen=True)
class MemoryLifecycleMemorySnapshot:
    """Visible memory footprint after one lifecycle stage."""

    active_object_count: int
    total_object_versions: int
    active_object_counts: dict[str, int]


@dataclass(frozen=True)
class MemoryLifecycleCostSnapshot:
    """Cumulative budget usage after one lifecycle stage."""

    total_cost: float
    generation_cost: float
    maintenance_cost: float
    retrieval_cost: float
    read_cost: float
    write_cost: float
    storage_cost: float
    offline_job_count: int


@dataclass(frozen=True)
class MemoryLifecycleStageReport:
    """Benchmark metrics captured after a concrete lifecycle stage."""

    stage_name: str
    ask: MemoryLifecycleAskMetrics
    memory: MemoryLifecycleMemorySnapshot
    cost: MemoryLifecycleCostSnapshot
    operation_notes: tuple[str, ...]


@dataclass(frozen=True)
class MemoryLifecycleBenchmarkReport:
    """Structured report for a full lifecycle benchmark run."""

    dataset_name: str
    source_path: str
    fixture_name: str
    run_id: str
    telemetry_path: str | None
    store_path: str | None
    bundle_count: int
    answer_case_count: int
    stage_reports: tuple[MemoryLifecycleStageReport, ...]
    frontend_debug_query: dict[str, str]
    notes: tuple[str, ...]


@dataclass
class _BundleRuntime:
    bundle_id: str
    task_id: str
    episode_id: str
    goal: str
    raw_object_ids: list[str]
    case_query_modes: dict[str, tuple[RetrieveQueryMode, ...]]
    answer_specs: list[dict[str, Any]]
    ref_map: dict[str, str]
    summary_object_id: str | None = None
    reflection_object_id: str | None = None


@dataclass(frozen=True)
class _AskCaseRuntime:
    case: EpisodeAnswerBenchCase
    query_modes: tuple[RetrieveQueryMode, ...]


def evaluate_memory_lifecycle_benchmark(
    dataset_name: str,
    *,
    source_path: str | Path,
    provider_selection: Mapping[str, object] | object | None = None,
    telemetry_path: str | Path | None = None,
    store_path: str | Path | None = None,
    run_id: str | None = None,
) -> MemoryLifecycleBenchmarkReport:
    """Run a staged benchmark across real memory primitives and offline maintenance."""

    payload = _load_source_payload(source_path)
    bundles_payload = list(payload["bundles"])
    fixture_name = f"{dataset_name} {payload['dataset_version']}"
    active_run_id = run_id or f"memory-lifecycle-{dataset_name}-{uuid4().hex[:10]}"
    provider_config = resolve_capability_provider_config(selection=provider_selection)
    capability_service = CapabilityService(provider_config=provider_config)
    recorder = JsonlTelemetryRecorder(telemetry_path) if telemetry_path is not None else None
    notes = (
        "TaskEpisode bootstrap is an explicit benchmark bridge because write_raw does not create "
        "episodes yet.",
        "Telemetry reuses the existing JSONL recorder and can be queried through the frontend "
        "debug timeline by run_id when the app points at the same telemetry path.",
    )

    with _store_context(store_path) as active_store_path:
        with SQLiteMemoryStore(active_store_path) as store:
            primitive_service = PrimitiveService(
                store,
                query_embedder=build_query_embedding,
                capability_service=CapabilityPortAdapter(service=capability_service),
                telemetry_recorder=recorder,
            )
            access_service = AccessService(
                store,
                query_embedder=build_query_embedding,
                capability_service=capability_service,
                telemetry_recorder=recorder,
            )
            offline_service = OfflineMaintenanceService(
                store,
                capability_service=capability_service,
                telemetry_recorder=recorder,
            )
            runtimes = _ingest_bundles(
                bundles_payload,
                primitive_service=primitive_service,
                recorder=recorder,
                run_id=active_run_id,
            )

            stage_reports = [
                _snapshot_stage(
                    stage_name="remember_only",
                    store=store,
                    access_service=access_service,
                    runtimes=runtimes,
                    run_id=active_run_id,
                    offline_job_count=0,
                    operation_notes=(
                        f"wrote {sum(len(runtime.raw_object_ids) for runtime in runtimes)} raw "
                        f"records across {len(runtimes)} episodes",
                        "bootstrapped TaskEpisode objects for reflection eligibility",
                    ),
                )
            ]

            summary_count = _run_summaries(primitive_service, runtimes, run_id=active_run_id)
            stage_reports.append(
                _snapshot_stage(
                    stage_name="summarized",
                    store=store,
                    access_service=access_service,
                    runtimes=runtimes,
                    run_id=active_run_id,
                    offline_job_count=0,
                    operation_notes=(f"created {summary_count} SummaryNote objects",),
                )
            )

            reflection_count = _run_reflections(primitive_service, runtimes, run_id=active_run_id)
            stage_reports.append(
                _snapshot_stage(
                    stage_name="reflected",
                    store=store,
                    access_service=access_service,
                    runtimes=runtimes,
                    run_id=active_run_id,
                    offline_job_count=0,
                    operation_notes=(f"created {reflection_count} ReflectionNote objects",),
                )
            )

            reprioritized_count = _run_reorganization(
                primitive_service,
                runtimes,
                run_id=active_run_id,
            )
            stage_reports.append(
                _snapshot_stage(
                    stage_name="reorganized",
                    store=store,
                    access_service=access_service,
                    runtimes=runtimes,
                    run_id=active_run_id,
                    offline_job_count=0,
                    operation_notes=(
                        f"reprioritized {reprioritized_count} summary/reflection objects",
                    ),
                )
            )

            promotion_result = _run_schema_promotion(
                offline_service,
                runtimes,
                provider_selection=_provider_selection_payload(provider_selection),
                run_id=active_run_id,
            )
            stage_reports.append(
                _snapshot_stage(
                    stage_name="schema_promoted",
                    store=store,
                    access_service=access_service,
                    runtimes=runtimes,
                    run_id=active_run_id,
                    offline_job_count=1,
                    operation_notes=(promotion_result,),
                )
            )

            return MemoryLifecycleBenchmarkReport(
                dataset_name=dataset_name,
                source_path=str(Path(source_path)),
                fixture_name=fixture_name,
                run_id=active_run_id,
                telemetry_path=str(Path(telemetry_path)) if telemetry_path is not None else None,
                store_path=str(active_store_path) if store_path is not None else None,
                bundle_count=len(runtimes),
                answer_case_count=sum(len(runtime.answer_specs) for runtime in runtimes),
                stage_reports=tuple(stage_reports),
                frontend_debug_query={"run_id": active_run_id},
                notes=notes,
            )


def write_memory_lifecycle_benchmark_report_json(
    path: str | Path,
    report: MemoryLifecycleBenchmarkReport,
) -> Path:
    """Persist a lifecycle benchmark report as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _load_source_payload(source_path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(source_path).read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or "bundles" not in payload
        or "dataset_version" not in payload
    ):
        raise ValueError("memory lifecycle benchmark requires a local slice JSON payload")
    return payload


class _store_context:
    def __init__(self, store_path: str | Path | None) -> None:
        self._explicit_path = Path(store_path) if store_path is not None else None
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self._active_path: Path | None = None

    def __enter__(self) -> Path:
        if self._explicit_path is not None:
            self._explicit_path.parent.mkdir(parents=True, exist_ok=True)
            self._active_path = self._explicit_path
            return self._active_path
        self._tmpdir = tempfile.TemporaryDirectory(prefix="memory_lifecycle_")
        self._active_path = Path(self._tmpdir.name) / "benchmark.sqlite3"
        return self._active_path

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._tmpdir is not None:
            self._tmpdir.cleanup()


def _ingest_bundles(
    bundles_payload: list[dict[str, Any]],
    *,
    primitive_service: PrimitiveService,
    recorder: JsonlTelemetryRecorder | None,
    run_id: str,
) -> list[_BundleRuntime]:
    runtimes: list[_BundleRuntime] = []
    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    for bundle_index, bundle in enumerate(bundles_payload, start=1):
        runtime = _BundleRuntime(
            bundle_id=str(bundle["bundle_id"]),
            task_id=str(bundle["task_id"]),
            episode_id=str(bundle["episode_id"]),
            goal=str(bundle["goal"]),
            raw_object_ids=[],
            case_query_modes={
                str(spec["case_key"]): tuple(
                    RetrieveQueryMode(mode) for mode in spec["query_modes"]
                )
                for spec in bundle.get("retrieval_specs", [])
            },
            answer_specs=list(bundle.get("answer_specs", [])),
            ref_map={"episode": str(bundle["episode_id"])},
        )
        bundle_time = start_time + timedelta(days=bundle_index)
        for record_index, raw_record in enumerate(bundle.get("raw_records", []), start=1):
            context = PrimitiveExecutionContext(
                actor="memory_lifecycle_benchmark",
                budget_scope_id=f"{run_id}:{runtime.bundle_id}:ingest",
                dev_mode=True,
                telemetry_run_id=run_id,
                telemetry_operation_id=f"lifecycle-ingest-{runtime.bundle_id}-{record_index}",
            )
            result = primitive_service.write_raw(
                {
                    "record_kind": str(raw_record["kind"]),
                    "content": {"text": str(raw_record["text"])},
                    "episode_id": runtime.episode_id,
                    "timestamp_order": record_index,
                },
                context,
            )
            if result.outcome is not PrimitiveOutcome.SUCCESS or result.response is None:
                raise RuntimeError(f"write_raw failed for {runtime.bundle_id}")
            object_id = str(result.response["object_id"])
            runtime.raw_object_ids.append(object_id)
            runtime.ref_map[f"record:{record_index}"] = object_id
        episode_object = {
            "id": runtime.episode_id,
            "type": "TaskEpisode",
            "content": {
                "title": runtime.goal,
                "result_summary": str(bundle["result"]),
            },
            "source_refs": list(runtime.raw_object_ids),
            "created_at": bundle_time.isoformat(),
            "updated_at": bundle_time.isoformat(),
            "version": 1,
            "status": "active",
            "priority": 0.65,
            "metadata": {
                "task_id": runtime.task_id,
                "goal": runtime.goal,
                "result": str(bundle["result"]),
                "success": bool(bundle.get("success", True)),
                "record_refs": list(runtime.raw_object_ids),
            },
        }
        primitive_service.store.insert_object(episode_object)
        _record_bootstrap_event(
            recorder,
            run_id=run_id,
            bundle_id=runtime.bundle_id,
            obj=episode_object,
        )
        runtimes.append(runtime)
    return runtimes


def _record_bootstrap_event(
    recorder: JsonlTelemetryRecorder | None,
    *,
    run_id: str,
    bundle_id: str,
    obj: dict[str, Any],
) -> None:
    if recorder is None:
        return
    recorder.record(
        TelemetryEvent(
            event_id=f"lifecycle-bootstrap-{bundle_id}",
            scope=TelemetryScope.OBJECT_DELTA,
            kind=TelemetryEventKind.STATE_DELTA,
            occurred_at=datetime.now(UTC),
            run_id=run_id,
            operation_id=f"lifecycle-bootstrap-{bundle_id}",
            object_id=str(obj["id"]),
            object_version=int(obj["version"]),
            actor="memory_lifecycle_benchmark",
            before={},
            after=obj,
            delta=obj,
            payload={"stage": "episode_bootstrap", "bundle_id": bundle_id},
        )
    )


def _run_summaries(
    primitive_service: PrimitiveService,
    runtimes: list[_BundleRuntime],
    *,
    run_id: str,
) -> int:
    created = 0
    for runtime in runtimes:
        result = primitive_service.summarize(
            {
                "input_refs": list(runtime.raw_object_ids),
                "summary_scope": "episode",
                "target_kind": "TaskEpisode",
            },
            PrimitiveExecutionContext(
                actor="memory_lifecycle_benchmark",
                budget_scope_id=f"{run_id}:{runtime.bundle_id}:summarize",
                dev_mode=True,
                telemetry_run_id=run_id,
                telemetry_operation_id=f"lifecycle-summarize-{runtime.bundle_id}",
            ),
        )
        if result.outcome is not PrimitiveOutcome.SUCCESS or result.response is None:
            raise RuntimeError(f"summarize failed for {runtime.bundle_id}")
        runtime.summary_object_id = str(result.response["summary_object_id"])
        runtime.ref_map["summary"] = runtime.summary_object_id
        created += 1
    return created


def _run_reflections(
    primitive_service: PrimitiveService,
    runtimes: list[_BundleRuntime],
    *,
    run_id: str,
) -> int:
    created = 0
    for runtime in runtimes:
        result = primitive_service.reflect(
            {"episode_id": runtime.episode_id, "focus": runtime.goal},
            PrimitiveExecutionContext(
                actor="memory_lifecycle_benchmark",
                budget_scope_id=f"{run_id}:{runtime.bundle_id}:reflect",
                dev_mode=True,
                telemetry_run_id=run_id,
                telemetry_operation_id=f"lifecycle-reflect-{runtime.bundle_id}",
            ),
        )
        if result.outcome is not PrimitiveOutcome.SUCCESS or result.response is None:
            raise RuntimeError(f"reflect failed for {runtime.bundle_id}")
        runtime.reflection_object_id = str(result.response["reflection_object_id"])
        runtime.ref_map["reflection"] = runtime.reflection_object_id
        created += 1
    return created


def _run_reorganization(
    primitive_service: PrimitiveService,
    runtimes: list[_BundleRuntime],
    *,
    run_id: str,
) -> int:
    target_refs = [
        object_id
        for runtime in runtimes
        for object_id in (runtime.summary_object_id, runtime.reflection_object_id)
        if object_id is not None
    ]
    if not target_refs:
        return 0
    result = primitive_service.reorganize_simple(
        {
            "target_refs": target_refs,
            "operation": "reprioritize",
            "reason": "boost reusable benchmark memories",
        },
        PrimitiveExecutionContext(
            actor="memory_lifecycle_benchmark",
            budget_scope_id=f"{run_id}:reorganize",
            dev_mode=True,
            telemetry_run_id=run_id,
            telemetry_operation_id="lifecycle-reorganize",
        ),
    )
    if result.outcome is not PrimitiveOutcome.SUCCESS or result.response is None:
        raise RuntimeError("reorganize_simple failed for lifecycle benchmark")
    return len(result.response["updated_ids"])


def _run_schema_promotion(
    offline_service: OfflineMaintenanceService,
    runtimes: list[_BundleRuntime],
    *,
    provider_selection: dict[str, Any] | None,
    run_id: str,
) -> str:
    target_refs = [
        runtime.reflection_object_id for runtime in runtimes if runtime.reflection_object_id
    ]
    if len(target_refs) < 2:
        return "skipped schema promotion because fewer than 2 reflections were available"
    job = new_offline_job(
        job_kind=OfflineJobKind.PROMOTE_SCHEMA,
        payload=PromoteSchemaJobPayload(
            target_refs=target_refs,
            reason="synthesize reusable memory schema from benchmark reflections",
        ),
    )
    result = offline_service.process_job(
        job,
        actor="memory_lifecycle_benchmark",
        dev_mode=True,
        provider_selection=provider_selection,
        telemetry_run_id=run_id,
    )
    if "schema_object_id" in result:
        return (
            f"promoted cross-episode schema {result['schema_object_id']} "
            f"from {len(target_refs)} reflections"
        )
    return f"schema promotion did not materialize: {result.get('reason', 'no schema created')}"


def _snapshot_stage(
    *,
    stage_name: str,
    store: SQLiteMemoryStore,
    access_service: AccessService,
    runtimes: list[_BundleRuntime],
    run_id: str,
    offline_job_count: int,
    operation_notes: tuple[str, ...],
) -> MemoryLifecycleStageReport:
    ask_metrics = _evaluate_asks(
        stage_name=stage_name,
        access_service=access_service,
        runtimes=runtimes,
        run_id=run_id,
    )
    active_objects = _latest_active_objects(store)
    counts = Counter(str(obj["type"]) for obj in active_objects)
    memory = MemoryLifecycleMemorySnapshot(
        active_object_count=len(active_objects),
        total_object_versions=len(store.iter_objects()),
        active_object_counts=dict(sorted(counts.items())),
    )
    cost = _cost_snapshot(store, offline_job_count=offline_job_count)
    return MemoryLifecycleStageReport(
        stage_name=stage_name,
        ask=ask_metrics,
        memory=memory,
        cost=cost,
        operation_notes=operation_notes,
    )


def _evaluate_asks(
    *,
    stage_name: str,
    access_service: AccessService,
    runtimes: list[_BundleRuntime],
    run_id: str,
) -> MemoryLifecycleAskMetrics:
    answer_scores: list[float] = []
    task_successes: list[float] = []
    candidate_hits: list[float] = []
    selected_hits: list[float] = []
    used_ids: list[str] = []
    pollution_bits: list[float] = []
    case_count = 0
    for runtime in runtimes:
        for ask_case in _build_stage_cases(runtime):
            response = access_service.run(
                {
                    "requested_mode": AccessMode.AUTO,
                    "query": ask_case.case.prompt,
                    "task_id": f"{runtime.task_id}::{stage_name}",
                    "capture_raw_exchange": True,
                    "query_modes": [mode.value for mode in ask_case.query_modes],
                },
                PrimitiveExecutionContext(
                    actor="memory_lifecycle_benchmark",
                    budget_scope_id=f"{run_id}:{stage_name}:ask",
                    dev_mode=True,
                    provider_selection=None,
                    telemetry_run_id=run_id,
                ),
            )
            response = AccessRunResponse.model_validate(response)
            score = score_answer(
                ask_case.case,
                GeneratedAnswer(
                    text=response.answer_text or "",
                    support_ids=tuple(response.answer_support_ids or response.used_object_ids),
                ),
            )
            answer_scores.append(score.answer_quality_score)
            task_successes.append(1.0 if score.task_success else 0.0)
            candidate_hits.append(_coverage(response.candidate_ids, ask_case.case.gold_fact_ids))
            selected_hits.append(
                _coverage(response.used_object_ids, ask_case.case.gold_memory_refs)
            )
            used_ids.extend(response.used_object_ids)
            gold_ids = set(ask_case.case.gold_fact_ids) | set(ask_case.case.gold_memory_refs)
            if response.used_object_ids:
                extraneous = sum(
                    1 for object_id in response.used_object_ids if object_id not in gold_ids
                )
                pollution_bits.append(extraneous / float(len(response.used_object_ids)))
            else:
                pollution_bits.append(0.0)
            case_count += 1

    unique_used = len(set(used_ids))
    reuse_rate = round((len(used_ids) - unique_used) / float(len(used_ids)), 4) if used_ids else 0.0
    return MemoryLifecycleAskMetrics(
        answer_case_count=case_count,
        average_answer_quality=_avg(answer_scores),
        task_success_rate=_avg(task_successes),
        candidate_hit_rate=_avg(candidate_hits),
        selected_hit_rate=_avg(selected_hits),
        reuse_rate=reuse_rate,
        pollution_rate=_avg(pollution_bits),
    )


def _build_stage_cases(runtime: _BundleRuntime) -> list[_AskCaseRuntime]:
    cases: list[_AskCaseRuntime] = []
    for answer_spec in runtime.answer_specs:
        gold_fact_ids = _resolve_refs(answer_spec.get("gold_fact_refs", []), runtime.ref_map)
        gold_memory_refs = _resolve_refs(answer_spec.get("gold_memory_refs", []), runtime.ref_map)
        if not gold_fact_ids and not gold_memory_refs:
            continue
        case = EpisodeAnswerBenchCase(
            case_id=f"{runtime.bundle_id}::{answer_spec['case_key']}",
            task_id=runtime.task_id,
            episode_id=runtime.episode_id,
            prompt=str(answer_spec["prompt"]),
            answer_kind=AnswerKind(str(answer_spec["answer_kind"])),
            required_fragments=tuple(
                str(item) for item in answer_spec.get("required_fragments", [])
            ),
            gold_fact_ids=tuple(gold_fact_ids or gold_memory_refs),
            gold_memory_refs=tuple(gold_memory_refs or gold_fact_ids),
            max_answer_tokens=int(answer_spec.get("max_answer_tokens", 32)),
        )
        cases.append(
            _AskCaseRuntime(
                case=case,
                query_modes=runtime.case_query_modes.get(
                    str(answer_spec["case_key"]),
                    (RetrieveQueryMode.KEYWORD,),
                ),
            )
        )
    return cases


def _resolve_refs(refs: list[str], ref_map: Mapping[str, str]) -> list[str]:
    return [ref_map[ref] for ref in refs if ref in ref_map]


def _coverage(
    actual_ids: list[str] | tuple[str, ...],
    gold_ids: list[str] | tuple[str, ...],
) -> float:
    if not gold_ids:
        return 0.0
    gold = set(gold_ids)
    return round(sum(1 for object_id in actual_ids if object_id in gold) / float(len(gold)), 4)


def _cost_snapshot(
    store: SQLiteMemoryStore,
    *,
    offline_job_count: int,
) -> MemoryLifecycleCostSnapshot:
    category_totals: dict[str, float] = {}
    total = 0.0
    for event in store.iter_budget_events():
        for cost in event.cost:
            key = cost.category.value if hasattr(cost.category, "value") else str(cost.category)
            category_totals[key] = category_totals.get(key, 0.0) + float(cost.amount)
            total += float(cost.amount)
    return MemoryLifecycleCostSnapshot(
        total_cost=round(total, 4),
        generation_cost=round(category_totals.get(PrimitiveCostCategory.GENERATION.value, 0.0), 4),
        maintenance_cost=round(
            category_totals.get(PrimitiveCostCategory.MAINTENANCE.value, 0.0),
            4,
        ),
        retrieval_cost=round(category_totals.get(PrimitiveCostCategory.RETRIEVAL.value, 0.0), 4),
        read_cost=round(category_totals.get(PrimitiveCostCategory.READ.value, 0.0), 4),
        write_cost=round(category_totals.get(PrimitiveCostCategory.WRITE.value, 0.0), 4),
        storage_cost=round(category_totals.get(PrimitiveCostCategory.STORAGE.value, 0.0), 4),
        offline_job_count=offline_job_count,
    )


def _latest_active_objects(store: SQLiteMemoryStore) -> list[dict[str, Any]]:
    latest_by_id: dict[str, dict[str, Any]] = {}
    for obj in store.iter_objects():
        object_id = str(obj["id"])
        existing = latest_by_id.get(object_id)
        if existing is None or int(obj["version"]) > int(existing["version"]):
            latest_by_id[object_id] = obj
    return [obj for obj in latest_by_id.values() if str(obj["status"]) == "active"]


def _avg(values: list[float]) -> float:
    return round(sum(values) / float(len(values)), 4) if values else 0.0


def _provider_selection_payload(
    provider_selection: Mapping[str, object] | object | None,
) -> dict[str, Any] | None:
    if provider_selection is None:
        return None
    if hasattr(provider_selection, "model_dump"):
        return provider_selection.model_dump(mode="json")
    if not isinstance(provider_selection, Mapping):
        raise TypeError("provider_selection must be mapping-like or expose model_dump()")
    return dict(provider_selection)


def _report_to_dict(report: MemoryLifecycleBenchmarkReport) -> dict[str, Any]:
    return {
        "dataset_name": report.dataset_name,
        "source_path": report.source_path,
        "fixture_name": report.fixture_name,
        "run_id": report.run_id,
        "telemetry_path": report.telemetry_path,
        "store_path": report.store_path,
        "bundle_count": report.bundle_count,
        "answer_case_count": report.answer_case_count,
        "frontend_debug_query": dict(report.frontend_debug_query),
        "notes": list(report.notes),
        "stage_reports": [
            {
                "stage_name": stage.stage_name,
                "operation_notes": list(stage.operation_notes),
                "ask": {
                    "answer_case_count": stage.ask.answer_case_count,
                    "average_answer_quality": stage.ask.average_answer_quality,
                    "task_success_rate": stage.ask.task_success_rate,
                    "candidate_hit_rate": stage.ask.candidate_hit_rate,
                    "selected_hit_rate": stage.ask.selected_hit_rate,
                    "reuse_rate": stage.ask.reuse_rate,
                    "pollution_rate": stage.ask.pollution_rate,
                },
                "memory": {
                    "active_object_count": stage.memory.active_object_count,
                    "total_object_versions": stage.memory.total_object_versions,
                    "active_object_counts": dict(stage.memory.active_object_counts),
                },
                "cost": {
                    "total_cost": stage.cost.total_cost,
                    "generation_cost": stage.cost.generation_cost,
                    "maintenance_cost": stage.cost.maintenance_cost,
                    "retrieval_cost": stage.cost.retrieval_cost,
                    "read_cost": stage.cost.read_cost,
                    "write_cost": stage.cost.write_cost,
                    "storage_cost": stage.cost.storage_cost,
                    "offline_job_count": stage.cost.offline_job_count,
                },
            }
            for stage in report.stage_reports
        ],
    }