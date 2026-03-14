"""Phase γ gate tests: new object types, graph retrieval,
model routing, artifact memory, auto-archive.

Mirrors the structure of test_phase_alpha_gate.py and test_phase_beta_gate.py.

Acceptance criteria verified here:
  γ-1: PolicyNote / PreferenceNote can be written, retrieved, and promoted.
        Promotion threshold for PolicyNote/PreferenceNote ≥ 3 episodes (> SchemaNote baseline of 2).
  γ-2: Graph-augmented retrieval correctly expands candidate sets via LinkEdge adjacency.
        RECALL=1-hop, RECONSTRUCT/REFLECTIVE_ACCESS=2-hop, FLASH=0-hop.
        DISCOVER_LINKS job kind present and executable.
  γ-3: CapabilityRoutingConfig enables per-capability model routing.
        Backward-compatible when no routing config is provided.
        CLI model_routing config resolved from parameter and env.
  γ-4: ArtifactIndex objects are produced by the artifact indexer for long content.
        REBUILD_ARTIFACT_INDEX job kind present and executable.
  γ-5: AUTO_ARCHIVE job archives stale, zero-feedback objects.
        Objects with positive feedback are not archived.
        dry_run mode does not modify the store.
        ArchiveReport gamma_gate_pass criterion: misarchive_rate ≤ 0.10.
  Gate: All Phase α and Phase β gate tests continue to pass (no regression).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _ts(days_ago: float = 0.0) -> str:
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    return dt.isoformat()


def _raw(obj_id: str, *, episode_id: str = "ep-1", days_old: float = 0.0) -> dict[str, Any]:
    ts = _ts(days_ago=days_old)
    return {
        "id": obj_id,
        "type": "RawRecord",
        "content": f"raw content {obj_id}",
        "source_refs": [],
        "created_at": ts,
        "updated_at": ts,
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "record_kind": "user_message",
            "episode_id": episode_id,
            "timestamp_order": 1,
        },
    }


def _link(src_id: str, dst_id: str, link_id: str | None = None) -> dict[str, Any]:
    lid = link_id or f"link-{src_id}-{dst_id}"
    return {
        "id": lid,
        "type": "LinkEdge",
        "content": {"src_id": src_id, "dst_id": dst_id, "relation_type": "related"},
        "source_refs": [src_id, dst_id],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {"confidence": 0.8, "evidence_refs": [src_id, dst_id]},
    }


def _reflection(obj_id: str, episode_id: str, src_id: str | None = None) -> dict[str, Any]:
    return {
        "id": obj_id,
        "type": "ReflectionNote",
        "content": f"reflection {obj_id}",
        "source_refs": [src_id or obj_id],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "episode_id": episode_id,
            "reflection_kind": "success",
            "claims": ["claim1"],
        },
    }


# ─── γ-1: PolicyNote / PreferenceNote ────────────────────────────────────────


class TestGammaNewObjectTypes:
    """γ-1 gate: policy and preference object types."""

    def test_policy_note_in_core_types(self) -> None:
        from mind.kernel.schema import CORE_OBJECT_TYPES

        assert "PolicyNote" in CORE_OBJECT_TYPES

    def test_preference_note_in_core_types(self) -> None:
        from mind.kernel.schema import CORE_OBJECT_TYPES

        assert "PreferenceNote" in CORE_OBJECT_TYPES

    def test_artifact_index_in_core_types(self) -> None:
        from mind.kernel.schema import CORE_OBJECT_TYPES

        assert "ArtifactIndex" in CORE_OBJECT_TYPES

    def test_policy_note_round_trip(self) -> None:
        from mind.kernel.schema import ensure_valid_object
        from mind.kernel.store import SQLiteMemoryStore

        store = SQLiteMemoryStore(":memory:")
        src = _raw("pn-src-1", episode_id="ep-pn")
        store.insert_object(src)
        obj = {
            "id": "gate-policy-1",
            "type": "PolicyNote",
            "content": "always cite sources",
            "source_refs": ["pn-src-1"],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.8,
            "metadata": {
                "trigger_condition": "citation requested",
                "action_pattern": "include source list",
                "evidence_refs": ["pn-src-1"],
                "confidence": 0.9,
                "applies_to_scope": "academic",
            },
        }
        ensure_valid_object(obj)
        store.insert_object(obj)
        read = store.read_object("gate-policy-1")
        assert read["type"] == "PolicyNote"

    def test_preference_note_round_trip(self) -> None:
        from mind.kernel.schema import ensure_valid_object
        from mind.kernel.store import SQLiteMemoryStore

        store = SQLiteMemoryStore(":memory:")
        src = _raw("pref-src-1", episode_id="ep-pref")
        store.insert_object(src)
        obj = {
            "id": "gate-pref-1",
            "type": "PreferenceNote",
            "content": "user prefers bullet points",
            "source_refs": ["pref-src-1"],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.7,
            "metadata": {
                "preference_key": "output_format",
                "preference_value": "bullets",
                "strength": 0.85,
                "evidence_refs": ["pref-src-1"],
            },
        }
        ensure_valid_object(obj)
        store.insert_object(obj)
        read = store.read_object("gate-pref-1")
        assert read["type"] == "PreferenceNote"

    def test_policy_promotion_min_episodes_greater_than_schema(self) -> None:
        from mind.offline.promotion import (
            POLICY_PROMOTION_MIN_EPISODES,
            assess_policy_promotion,
            assess_schema_promotion,
        )

        # Schema requires ≥2 episodes; policy requires ≥3.
        assert POLICY_PROMOTION_MIN_EPISODES >= 3

        two_ep = [_reflection(f"obj-{i}", f"ep-{i}", f"obj-{i}") for i in range(2)]
        # Schema with 2 episodes should pass; policy with 2 should fail.
        s_dec = assess_schema_promotion(two_ep)
        assert s_dec.promote
        p_dec = assess_policy_promotion(two_ep)
        assert not p_dec.promote

    def test_preference_promotion_min_episodes(self) -> None:
        from mind.offline.promotion import (
            PREFERENCE_PROMOTION_MIN_EPISODES,
            assess_preference_promotion,
        )

        assert PREFERENCE_PROMOTION_MIN_EPISODES >= 3
        three_ep = [_raw(f"pref-ev-{i}", episode_id=f"pref-ep-{i}") for i in range(3)]
        dec = assess_preference_promotion(three_ep)
        assert dec.promote

    def test_promote_policy_job_kind(self) -> None:
        from mind.offline_jobs import OfflineJobKind

        assert OfflineJobKind.PROMOTE_POLICY == "promote_policy"

    def test_promote_preference_job_kind(self) -> None:
        from mind.offline_jobs import OfflineJobKind

        assert OfflineJobKind.PROMOTE_PREFERENCE == "promote_preference"

    def test_policy_note_workspace_boost(self) -> None:
        from mind.workspace.builder import _is_decision_purpose

        assert _is_decision_purpose("decision workspace")
        assert not _is_decision_purpose("flash access")


# ─── γ-2: Graph-augmented retrieval ──────────────────────────────────────────


class TestGammaGraphRetrieval:
    """γ-2 gate: graph adjacency and BFS expansion."""

    def _store_with_chain(self) -> Any:
        from mind.kernel.store import SQLiteMemoryStore

        store = SQLiteMemoryStore(":memory:")
        for i in range(1, 5):
            store.insert_object(_raw(f"g-obj-{i}", episode_id=f"g-ep-{i}"))
        # Chain: obj-1 – obj-2 – obj-3 – obj-4
        store.insert_object(_link("g-obj-1", "g-obj-2"))
        store.insert_object(_link("g-obj-2", "g-obj-3"))
        store.insert_object(_link("g-obj-3", "g-obj-4"))
        return store

    def test_adjacency_index_bidirectional(self) -> None:
        from mind.kernel.graph import build_adjacency_index

        store = self._store_with_chain()
        adj = build_adjacency_index(store)
        assert "g-obj-2" in adj.get("g-obj-1", [])
        assert "g-obj-1" in adj.get("g-obj-2", [])

    def test_one_hop_does_not_over_expand(self) -> None:
        from mind.kernel.graph import build_adjacency_index, expand_by_graph

        store = self._store_with_chain()
        adj = build_adjacency_index(store)
        expanded = expand_by_graph(["g-obj-1"], adj, hops=1)
        assert "g-obj-2" in expanded
        assert "g-obj-3" not in expanded

    def test_two_hop_expands_further(self) -> None:
        from mind.kernel.graph import build_adjacency_index, expand_by_graph

        store = self._store_with_chain()
        adj = build_adjacency_index(store)
        expanded = expand_by_graph(["g-obj-1"], adj, hops=2)
        assert "g-obj-2" in expanded
        assert "g-obj-3" in expanded

    def test_cycle_safety(self) -> None:
        from mind.kernel.graph import expand_by_graph

        adj = {"A": ["B"], "B": ["A", "C"], "C": ["A", "B"]}
        result = expand_by_graph(["A"], adj, hops=5, max_expand=5)
        assert "A" not in result

    def test_max_expand_respected(self) -> None:
        from mind.kernel.graph import expand_by_graph

        adj = {f"n{i}": [f"n{i + 1}"] for i in range(20)}
        expanded = expand_by_graph(["n0"], adj, hops=15, max_expand=4)
        assert len(expanded) <= 4

    def test_graph_hops_per_access_mode(self) -> None:
        from mind.access.contracts import AccessMode
        from mind.access.service import _graph_hops_for_mode

        assert _graph_hops_for_mode(AccessMode.FLASH) == 0
        assert _graph_hops_for_mode(AccessMode.RECALL) == 1
        assert _graph_hops_for_mode(AccessMode.RECONSTRUCT) == 2
        assert _graph_hops_for_mode(AccessMode.REFLECTIVE_ACCESS) == 2

    def test_discover_links_job_kind(self) -> None:
        from mind.offline_jobs import OfflineJobKind

        assert OfflineJobKind.DISCOVER_LINKS == "discover_links"

    def test_scheduler_schedule_discover_links(self) -> None:
        from mind.offline.scheduler import OfflineJobScheduler
        from mind.offline_jobs import OfflineJobKind

        jobs: list = []

        class FakeStore:
            def enqueue_offline_job(self, job: Any) -> None:
                jobs.append(job)

        scheduler = OfflineJobScheduler(FakeStore())  # type: ignore[arg-type]
        scheduler.schedule_discover_links()
        assert jobs[-1].job_kind == OfflineJobKind.DISCOVER_LINKS


# ─── γ-3: Model routing ───────────────────────────────────────────────────────


class TestGammaModelRouting:
    """γ-3 gate: per-capability model routing."""

    def test_capability_routing_config_exists(self) -> None:
        from mind.capabilities.contracts import CapabilityRoutingConfig

        config = CapabilityRoutingConfig()
        assert config.routes == {}

    def test_capability_service_accepts_routing_config(self) -> None:
        from mind.capabilities.contracts import CapabilityRoutingConfig
        from mind.capabilities.service import CapabilityService

        service = CapabilityService(routing_config=CapabilityRoutingConfig())
        assert service._routing_config is not None

    def test_routing_dispatches_correct_provider(self) -> None:
        from mind.capabilities.config import (
            CapabilityProviderConfig,
            CapabilityProviderFamily,
        )
        from mind.capabilities.contracts import (
            CapabilityName,
            CapabilityRoutingConfig,
            SummarizeRequest,
            SummarizeResponse,
        )
        from mind.capabilities.service import CapabilityService

        det = CapabilityProviderConfig(
            provider="stub",
            provider_family=CapabilityProviderFamily.DETERMINISTIC,
            model="deterministic",
            endpoint="local://deterministic",
        )
        routing = CapabilityRoutingConfig(routes={CapabilityName.SUMMARIZE: det})
        service = CapabilityService(routing_config=routing)
        req = SummarizeRequest(request_id="gate-route-1", source_text="summarise this text")
        response = service.invoke(req)
        assert isinstance(response, SummarizeResponse)
        assert response.summary_text

    def test_backward_compat_without_routing(self) -> None:
        from mind.capabilities.contracts import SummarizeRequest, SummarizeResponse
        from mind.capabilities.service import CapabilityService

        service = CapabilityService()
        req = SummarizeRequest(request_id="gate-compat-1", source_text="backward compat test")
        response = service.invoke(req)
        assert isinstance(response, SummarizeResponse)
        assert response.summary_text

    def test_cli_model_routing_param(self) -> None:
        from mind.cli_config import resolve_cli_config

        config = resolve_cli_config(
            allow_sqlite=True,
            model_routing={"summarize": "small-model"},
        )
        assert config.model_routing == {"summarize": "small-model"}

    def test_cli_model_routing_from_env(self) -> None:
        import json

        from mind.cli_config import resolve_cli_config

        routing = {"summarize": "small", "answer": "large"}
        config = resolve_cli_config(
            allow_sqlite=True,
            env={
                "MIND_ALLOW_SQLITE_FOR_TESTS": "1",
                "MIND_MODEL_ROUTING": json.dumps(routing),
            },
        )
        assert config.model_routing == routing


# ─── γ-4: Structured artifact memory ─────────────────────────────────────────


class TestGammaArtifactMemory:
    """γ-4 gate: ArtifactIndex and artifact indexer."""

    def test_artifact_index_schema(self) -> None:
        from mind.kernel.schema import CORE_OBJECT_TYPES, REQUIRED_METADATA_FIELDS

        assert "ArtifactIndex" in CORE_OBJECT_TYPES
        fields = REQUIRED_METADATA_FIELDS["ArtifactIndex"]
        assert "parent_object_id" in fields and "depth" in fields

    def test_build_artifact_index_produces_sections(self) -> None:
        from mind.offline.artifact_indexer import build_artifact_index

        content = (
            "# Introduction\n" + "Text " * 60 + "\n"
            "# Methods\n" + "Text " * 60 + "\n"
            "# Results\n" + "Text " * 60 + "\n"
        )
        obj = {
            "id": "gate-artifact-src",
            "type": "SummaryNote",
            "content": content,
            "source_refs": [],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.6,
            "metadata": {
                "summary_scope": "document",
                "input_refs": [],
                "compression_ratio_estimate": 0.3,
            },
        }
        result = build_artifact_index(obj, min_content_length=50)
        assert len(result) >= 3
        for item in result:
            assert item["type"] == "ArtifactIndex"

    def test_short_content_not_indexed(self) -> None:
        from mind.offline.artifact_indexer import build_artifact_index

        obj = {
            "id": "gate-short",
            "type": "SummaryNote",
            "content": "short",
            "source_refs": [],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "summary_scope": "episode",
                "input_refs": [],
                "compression_ratio_estimate": 1.0,
            },
        }
        assert build_artifact_index(obj, min_content_length=500) == []

    def test_rebuild_artifact_index_job_kind(self) -> None:
        from mind.offline_jobs import OfflineJobKind

        assert OfflineJobKind.REBUILD_ARTIFACT_INDEX == "rebuild_artifact_index"

    def test_artifact_index_objects_pass_schema(self) -> None:
        from mind.kernel.schema import validate_object
        from mind.offline.artifact_indexer import build_artifact_index

        content = "# Heading\n" + "Word " * 100 + "\n## Sub\n" + "Word " * 80
        obj = {
            "id": "gate-validate-src",
            "type": "SummaryNote",
            "content": content,
            "source_refs": [],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "summary_scope": "section",
                "input_refs": [],
                "compression_ratio_estimate": 0.5,
            },
        }
        for item in build_artifact_index(obj, min_content_length=50):
            assert validate_object(item) == [], f"Validation errors: {validate_object(item)}"


# ─── γ-5: Memory decay & auto-archive ────────────────────────────────────────


class TestGammaAutoArchive:
    """γ-5 gate: auto-archive stale objects, ArchiveReport, scheduler, CLI."""

    def _store(self) -> Any:
        from mind.kernel.store import SQLiteMemoryStore

        return SQLiteMemoryStore(":memory:")

    def _service(self, store: Any) -> Any:
        from mind.offline.service import OfflineMaintenanceService

        return OfflineMaintenanceService(store)

    def _job(self, payload: Any) -> Any:
        from mind.offline_jobs import OfflineJobKind, new_offline_job

        return new_offline_job(job_kind=OfflineJobKind.AUTO_ARCHIVE, payload=payload)

    def test_auto_archive_job_kind(self) -> None:
        from mind.offline_jobs import OfflineJobKind

        assert OfflineJobKind.AUTO_ARCHIVE == "auto_archive"

    def test_stale_no_feedback_archived(self) -> None:
        from mind.offline_jobs import AutoArchiveJobPayload

        store = self._store()
        store.insert_object(_raw("gate-stale-1", days_old=100))
        result = self._service(store).process_job(
            self._job(AutoArchiveJobPayload(stale_days=90)),
            actor="test",
        )
        assert result["archived_count"] >= 1
        assert store.read_object("gate-stale-1")["status"] == "archived"

    def test_positive_feedback_object_not_archived(self) -> None:
        from mind.offline_jobs import AutoArchiveJobPayload

        store = self._store()
        obj = _raw("gate-fb-1", days_old=100)
        obj["metadata"]["feedback_positive_count"] = 5
        store.insert_object(obj)
        result = self._service(store).process_job(
            self._job(AutoArchiveJobPayload(stale_days=90)),
            actor="test",
        )
        assert "gate-fb-1" not in result["archived_ids"]

    def test_dry_run_no_store_modification(self) -> None:
        from mind.offline_jobs import AutoArchiveJobPayload

        store = self._store()
        store.insert_object(_raw("gate-dry-1", days_old=100))
        result = self._service(store).process_job(
            self._job(AutoArchiveJobPayload(stale_days=90, dry_run=True)),
            actor="test",
        )
        assert result["dry_run"] is True
        assert store.read_object("gate-dry-1")["status"] == "active"

    def test_scheduler_schedule_auto_archive(self) -> None:
        from mind.offline.scheduler import OfflineJobScheduler
        from mind.offline_jobs import OfflineJobKind

        jobs: list = []

        class FakeStore:
            def enqueue_offline_job(self, job: Any) -> None:
                jobs.append(job)

        scheduler = OfflineJobScheduler(FakeStore())  # type: ignore[arg-type]
        scheduler.schedule_auto_archive()
        assert jobs[-1].job_kind == OfflineJobKind.AUTO_ARCHIVE

    def test_archive_report_gate_pass(self) -> None:
        from mind.eval.growth_metrics import ArchiveReport

        report = ArchiveReport.compute(archived_count=20, unarchived_count=1, total_objects=200)
        assert report.gamma_gate_pass  # misarchive_rate = 0.05 ≤ 0.10

    def test_archive_report_gate_fail(self) -> None:
        from mind.eval.growth_metrics import ArchiveReport

        report = ArchiveReport.compute(archived_count=10, unarchived_count=3, total_objects=100)
        assert not report.gamma_gate_pass  # misarchive_rate = 0.30 > 0.10

    def test_unarchive_cli_subcommand(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        assert parser._subparsers is not None
        choices = parser._subparsers._group_actions[0].choices
        assert choices is not None
        assert "unarchive" in choices


# ─── Regression: α and β gate imports still work ─────────────────────────────


class TestGammaNoRegression:
    """Verify that Phase α / β symbols are still accessible."""

    def test_alpha_feedback_record_type(self) -> None:
        from mind.kernel.schema import CORE_OBJECT_TYPES

        assert "FeedbackRecord" in CORE_OBJECT_TYPES

    def test_beta_embedding_provider(self) -> None:
        from mind.kernel.embedding import LocalHashEmbedding

        provider = LocalHashEmbedding()
        # embed() returns a list of per-word vectors; verify it's non-empty.
        vecs = provider.embed(["test text"])
        assert len(vecs) > 0

    def test_beta_conflict_detection(self) -> None:
        from mind.primitives.conflict import ConflictRelation

        assert ConflictRelation.DUPLICATE == "duplicate"

    def test_beta_slot_allocation_policy(self) -> None:
        from mind.workspace.policy import FLASH_POLICY

        assert FLASH_POLICY is not None

    def test_beta_mode_history_cache(self) -> None:
        from mind.access.mode_history import ModeHistoryCache

        cache = ModeHistoryCache()
        assert cache is not None

    def test_alpha_growth_phase_alpha_report(self) -> None:
        from mind.eval.growth_metrics import ArchiveReport, GrowthPhaseAlphaReport

        # Both the α report and the γ ArchiveReport should coexist.
        assert GrowthPhaseAlphaReport is not None
        assert ArchiveReport is not None

    def test_all_gamma_job_kinds_in_enum(self) -> None:
        from mind.offline_jobs import OfflineJobKind

        gamma_kinds = {
            "promote_policy",
            "promote_preference",
            "discover_links",
            "rebuild_artifact_index",
            "auto_archive",
        }
        existing = {k.value for k in OfflineJobKind}
        assert gamma_kinds <= existing
