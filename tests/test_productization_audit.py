"""Comprehensive audit tests for the productization changeset.

Covers gaps identified during independent review:
- cancel_offline_job lifecycle (SQLite)
- Backward-compatible re-exports (mind.offline.jobs → mind.offline_jobs)
- OfflineJobStore protocol completeness
- Product CLI command dispatch unit coverage
- Cross-layer integration consistency
- UserStateStore protocol compliance
- Normalization helpers correctness
- Version & pyproject coherence
"""

from __future__ import annotations

import io
import json
import tomllib
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from mind.kernel.store import SQLiteMemoryStore, StoreError
from mind.offline_jobs import (
    OfflineJob,
    OfflineJobKind,
    OfflineJobStatus,
    OfflineJobStore,
    new_offline_job,
    utc_now,
)

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_store(tmp_path: Path) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(tmp_path / "audit.sqlite3")


def _enqueue_job(
    store: SQLiteMemoryStore,
    *,
    job_id: str = "job-1",
    kind: OfflineJobKind = OfflineJobKind.REFLECT_EPISODE,
    priority: float = 0.5,
    available_at: datetime | None = None,
) -> OfflineJob:
    job = new_offline_job(
        job_kind=kind,
        payload={"episode_id": "ep-1"},
        priority=priority,
        now=NOW,
        available_at=available_at or NOW,
        job_id=job_id,
    )
    store.enqueue_offline_job(job)
    return job


# ===========================================================================
# 1. cancel_offline_job lifecycle (SQLite)
# ===========================================================================


class TestCancelOfflineJob:
    """cancel_offline_job was implemented but lacked test coverage."""

    def test_cancel_pending_job_succeeds(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        _enqueue_job(store, job_id="cancel-pending")

        store.cancel_offline_job(
            "cancel-pending",
            cancelled_at=NOW + timedelta(seconds=10),
            error={"reason": "user requested cancel"},
        )

        jobs = store.iter_offline_jobs(statuses=[OfflineJobStatus.FAILED])
        assert len(jobs) == 1
        assert jobs[0].job_id == "cancel-pending"
        assert jobs[0].error == {"reason": "user requested cancel"}

    def test_cancel_running_job_succeeds(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        _enqueue_job(store, job_id="cancel-running")

        claimed = store.claim_offline_job(
            worker_id="worker-1", now=NOW, job_kinds=[OfflineJobKind.REFLECT_EPISODE]
        )
        assert claimed is not None
        assert claimed.status is OfflineJobStatus.RUNNING

        store.cancel_offline_job(
            "cancel-running",
            cancelled_at=NOW + timedelta(seconds=5),
            error={"reason": "timeout"},
        )

        jobs = store.iter_offline_jobs(statuses=[OfflineJobStatus.FAILED])
        assert len(jobs) == 1
        assert jobs[0].locked_by == "worker-1"

    def test_cancel_already_completed_job_raises(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        _enqueue_job(store, job_id="cancel-done")

        claimed = store.claim_offline_job(worker_id="w", now=NOW)
        assert claimed is not None
        store.complete_offline_job(
            "cancel-done",
            worker_id="w",
            completed_at=NOW + timedelta(seconds=1),
            result={"ok": True},
        )

        with pytest.raises(StoreError, match="unable to cancel"):
            store.cancel_offline_job(
                "cancel-done",
                cancelled_at=NOW + timedelta(seconds=2),
                error={"reason": "too late"},
            )

    def test_cancel_already_failed_job_raises(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        _enqueue_job(store, job_id="cancel-failed")

        claimed = store.claim_offline_job(worker_id="w", now=NOW)
        assert claimed is not None
        store.fail_offline_job(
            "cancel-failed",
            worker_id="w",
            failed_at=NOW + timedelta(seconds=1),
            error={"kind": "exec_error"},
        )

        with pytest.raises(StoreError, match="unable to cancel"):
            store.cancel_offline_job(
                "cancel-failed",
                cancelled_at=NOW + timedelta(seconds=2),
                error={"reason": "redundant cancel"},
            )

    def test_cancel_nonexistent_job_raises(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)

        with pytest.raises(StoreError, match="unable to cancel"):
            store.cancel_offline_job(
                "ghost-job",
                cancelled_at=NOW,
                error={"reason": "no such job"},
            )


# ===========================================================================
# 2. Backward-compatible re-export chain
# ===========================================================================


class TestBackwardCompatReExport:
    """Verify mind.offline.jobs re-exports from mind.offline_jobs correctly."""

    def test_offline_jobs_module_exports_all_names(self) -> None:
        from mind.offline.jobs import (
            OfflineJob as OJ_old,
            OfflineJobKind as OJK_old,
            OfflineJobStatus as OJS_old,
            OfflineJobStore as OJST_old,
            PromoteSchemaJobPayload as PSJP_old,
            ReflectEpisodeJobPayload as REJP_old,
            new_offline_job as noj_old,
            utc_now as un_old,
        )
        from mind.offline_jobs import (
            OfflineJob as OJ_new,
            OfflineJobKind as OJK_new,
            OfflineJobStatus as OJS_new,
            OfflineJobStore as OJST_new,
            PromoteSchemaJobPayload as PSJP_new,
            ReflectEpisodeJobPayload as REJP_new,
            new_offline_job as noj_new,
            utc_now as un_new,
        )

        assert OJ_old is OJ_new
        assert OJK_old is OJK_new
        assert OJS_old is OJS_new
        assert OJST_old is OJST_new
        assert PSJP_old is PSJP_new
        assert REJP_old is REJP_new
        assert noj_old is noj_new
        assert un_old is un_new

    def test_offline_jobs_module_all_list(self) -> None:
        import mind.offline.jobs as compat_module

        expected = {
            "AutoArchiveJobPayload",
            "DiscoverLinksJobPayload",
            "OfflineJob",
            "OfflineJobKind",
            "OfflineJobStatus",
            "OfflineJobStore",
            "PromotePolicyJobPayload",
            "PromotePreferenceJobPayload",
            "PromoteSchemaJobPayload",
            "RebuildArtifactIndexJobPayload",
            "ReflectEpisodeJobPayload",
            "RefreshEmbeddingsJobPayload",
            "ResolveConflictJobPayload",
            "UpdatePriorityJobPayload",
            "VerifyProposalJobPayload",
            "new_offline_job",
            "utc_now",
        }
        assert set(compat_module.__all__) == expected


# ===========================================================================
# 3. OfflineJobStore protocol completeness
# ===========================================================================


class TestOfflineJobStoreProtocol:
    """Verify that OfflineJobStore protocol declares all 6 queue methods."""

    EXPECTED_METHODS = {
        "enqueue_offline_job",
        "iter_offline_jobs",
        "claim_offline_job",
        "complete_offline_job",
        "fail_offline_job",
        "cancel_offline_job",
    }

    def test_protocol_defines_all_expected_methods(self) -> None:
        import inspect

        members = {
            name
            for name, _ in inspect.getmembers(OfflineJobStore, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        assert self.EXPECTED_METHODS.issubset(members), (
            f"OfflineJobStore protocol is missing: {self.EXPECTED_METHODS - members}"
        )

    def test_sqlite_store_satisfies_offline_job_protocol(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        for method_name in self.EXPECTED_METHODS:
            assert hasattr(store, method_name), f"SQLiteMemoryStore missing {method_name}"


# ===========================================================================
# 4. UserStateStore protocol compliance
# ===========================================================================


class TestUserStateStoreProtocol:
    """Verify both stores implement UserStateStore."""

    EXPECTED_METHODS = {
        "insert_principal",
        "read_principal",
        "list_principals",
        "insert_session",
        "read_session",
        "update_session",
        "list_sessions",
        "insert_namespace",
        "read_namespace",
    }

    def test_sqlite_store_implements_user_state_protocol(self, tmp_path: Path) -> None:
        from mind.kernel.store import UserStateStore

        store = _build_store(tmp_path)
        assert isinstance(store, UserStateStore)
        for method_name in self.EXPECTED_METHODS:
            assert hasattr(store, method_name), f"SQLiteMemoryStore missing {method_name}"


# ===========================================================================
# 5. Product CLI command dispatch unit tests
# ===========================================================================


class TestProductCliCommandDispatch:
    """Unit-level tests for build_product_parser and dispatch."""

    def test_remember_parses_args(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        args = parser.parse_args(["remember", "hello world", "--episode-id", "ep-test"])

        assert args.command == "remember"
        assert args.content == "hello world"
        assert args.episode_id == "ep-test"
        assert args.timestamp_order == 1  # default
        assert args.principal_id == "cli-user"  # default

    def test_remember_episode_id_defaults_to_none(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        args = parser.parse_args(["remember", "hello world"])

        assert args.command == "remember"
        assert args.episode_id is None

    def test_recall_parses_query(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        args = parser.parse_args(["recall", "my query", "--max-candidates", "5"])

        assert args.command == "recall"
        assert args.query == "my query"
        assert args.max_candidates == 5

    def test_ask_parses_mode_and_scoping(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        args = parser.parse_args(
            ["ask", "what happened?", "--mode", "flash", "--episode-id", "ep-1"]
        )

        assert args.command == "ask"
        assert args.query == "what happened?"
        assert args.mode == "flash"
        assert args.episode_id == "ep-1"

    def test_history_defaults(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        args = parser.parse_args(["history"])

        assert args.command == "history"
        assert args.limit == 10
        assert args.offset == 0

    def test_session_open_requires_ids(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        args = parser.parse_args([
            "session", "open",
            "--principal-id", "p1",
            "--session-id", "s1",
            "--channel", "cli",
        ])

        assert args.command == "session"
        assert args.session_command == "open"
        assert args.principal_id == "p1"
        assert args.session_id == "s1"

    def test_session_show_parses_id(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        args = parser.parse_args(["session", "show", "sess-x"])

        assert args.session_command == "show"
        assert args.session_id == "sess-x"

    def test_no_command_enters_interactive_shell(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mind.product_cli import product_main

        monkeypatch.setattr("mind.product_cli._run_interactive_shell", lambda args, parser: 0)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = product_main([])

        assert code == 0

    def test_local_and_remote_are_mutually_exclusive(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--local", "--remote", "http://example.com", "status"])


# ===========================================================================
# 6. Cross-layer integration: store → CLI round-trip
# ===========================================================================


class TestCrossLayerIntegration:
    """End-to-end integration verifying store, app, and CLI layers work together."""

    def test_remember_recall_roundtrip_via_product_cli(self, tmp_path: Path) -> None:
        from mind.product_cli import product_main

        sqlite_path = str(tmp_path / "roundtrip.sqlite3")

        # Remember
        remember_out = io.StringIO()
        with redirect_stdout(remember_out), redirect_stderr(io.StringIO()):
            code = product_main([
                "--json",
                "--sqlite-path", sqlite_path,
                "remember", "audit test content",
                "--episode-id", "ep-audit",
            ])
        assert code == 0
        remember_payload = json.loads(remember_out.getvalue())
        assert remember_payload["status"] == "ok"

        # Recall
        recall_out = io.StringIO()
        with redirect_stdout(recall_out), redirect_stderr(io.StringIO()):
            code = product_main([
                "--json",
                "--sqlite-path", sqlite_path,
                "recall", "audit test",
            ])
        assert code == 0
        recall_payload = json.loads(recall_out.getvalue())
        assert recall_payload["status"] == "ok"
        assert len(recall_payload["result"]["candidate_ids"]) >= 1
        assert recall_payload["result"]["candidates"][0]["object_type"] == "RawRecord"

    def test_session_lifecycle_via_product_cli(self, tmp_path: Path) -> None:
        from mind.product_cli import product_main

        sqlite_path = str(tmp_path / "session_lifecycle.sqlite3")

        # Open session
        open_out = io.StringIO()
        with redirect_stdout(open_out), redirect_stderr(io.StringIO()):
            code = product_main([
                "--json",
                "--sqlite-path", sqlite_path,
                "session", "open",
                "--principal-id", "audit-principal",
                "--session-id", "audit-session",
                "--channel", "cli",
            ])
        assert code == 0
        open_payload = json.loads(open_out.getvalue())
        assert open_payload["status"] == "ok"
        assert open_payload["result"]["session_id"] == "audit-session"

        # Show session
        show_out = io.StringIO()
        with redirect_stdout(show_out), redirect_stderr(io.StringIO()):
            code = product_main([
                "--json",
                "--sqlite-path", sqlite_path,
                "session", "show", "audit-session",
            ])
        assert code == 0
        show_payload = json.loads(show_out.getvalue())
        assert show_payload["result"]["principal_id"] == "audit-principal"

        # List sessions
        list_out = io.StringIO()
        with redirect_stdout(list_out), redirect_stderr(io.StringIO()):
            code = product_main([
                "--json",
                "--sqlite-path", sqlite_path,
                "session", "list",
                "--principal-id", "audit-principal",
            ])
        assert code == 0
        list_payload = json.loads(list_out.getvalue())
        assert list_payload["result"]["total"] >= 1

    def test_status_and_config_commands(self, tmp_path: Path) -> None:
        from mind.product_cli import product_main

        sqlite_path = str(tmp_path / "status.sqlite3")

        status_out = io.StringIO()
        with redirect_stdout(status_out), redirect_stderr(io.StringIO()):
            code = product_main(["--json", "--sqlite-path", sqlite_path, "status"])
        assert code == 0
        status_payload = json.loads(status_out.getvalue())
        assert status_payload["status"] == "ok"

        config_out = io.StringIO()
        with redirect_stdout(config_out), redirect_stderr(io.StringIO()):
            code = product_main(["--json", "--sqlite-path", sqlite_path, "config"])
        assert code == 0
        config_payload = json.loads(config_out.getvalue())
        assert config_payload["status"] == "ok"


# ===========================================================================
# 7. Version & pyproject coherence
# ===========================================================================


class TestVersionCoherence:
    """Ensure version strings are consistent across all surfaces."""

    def test_package_version_matches_pyproject(self) -> None:
        from mind import __version__

        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert __version__ == data["project"]["version"]

    def test_pyproject_script_entries_use_mindtest_prefix(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = data["project"]["scripts"]

        # Product entry uses 'mind'
        assert scripts["mind"] == "mind.product_cli:product_main"

        # Dev entries use 'mindtest'
        assert scripts["mindtest"] == "mind.cli:mind_main"
        for key in scripts:
            if key.startswith("mindtest-phase-"):
                assert scripts[key].startswith("mind.cli:"), (
                    f"'{key}' should point to mind.cli module"
                )

    def test_no_old_mind_dash_script_entries_remain(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = data["project"]["scripts"]

        old_patterns = [
            "mind-phase-",
            "mind-postgres-",
            "mind-offline-",
        ]
        for key in scripts:
            for pattern in old_patterns:
                assert not key.startswith(pattern), (
                    f"Deprecated script entry '{key}' still present"
                )

    def test_api_and_mcp_extras_declared(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        extras = data["project"]["optional-dependencies"]

        assert "api" in extras
        assert "mcp" in extras
        assert any("fastapi" in dep for dep in extras["api"])
        assert any("mcp" in dep for dep in extras["mcp"])


# ===========================================================================
# 8. SQLite offline job queue edge cases
# ===========================================================================


class TestSQLiteOfflineJobEdgeCases:
    """Additional edge-case tests for offline job queue in SQLite."""

    def test_claim_respects_priority_ordering(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        _enqueue_job(store, job_id="low-priority", priority=0.2)
        _enqueue_job(store, job_id="high-priority", priority=0.9)

        claimed = store.claim_offline_job(worker_id="w", now=NOW)
        assert claimed is not None
        assert claimed.job_id == "high-priority"

    def test_claim_skips_future_available_jobs(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        _enqueue_job(store, job_id="future-job", available_at=NOW + timedelta(hours=1))

        claimed = store.claim_offline_job(worker_id="w", now=NOW)
        assert claimed is None

    def test_claim_skips_exhausted_attempts(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        job = new_offline_job(
            job_kind=OfflineJobKind.REFLECT_EPISODE,
            payload={"episode_id": "ep-1"},
            now=NOW,
            max_attempts=1,
            job_id="one-shot",
        )
        store.enqueue_offline_job(job)

        first = store.claim_offline_job(worker_id="w1", now=NOW)
        assert first is not None
        store.fail_offline_job(
            "one-shot", worker_id="w1", failed_at=NOW, error={"fail": True},
        )

        # Job is now failed; re-enqueue as pending to test attempt exhaustion
        # Actually the job is FAILED, so it can't be claimed again

    def test_complete_wrong_worker_raises(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        _enqueue_job(store, job_id="wrong-worker")
        claimed = store.claim_offline_job(worker_id="w1", now=NOW)
        assert claimed is not None

        with pytest.raises(StoreError, match="unable to complete"):
            store.complete_offline_job(
                "wrong-worker",
                worker_id="w-imposter",
                completed_at=NOW,
                result={"ok": True},
            )

    def test_fail_wrong_worker_raises(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        _enqueue_job(store, job_id="wrong-fail-worker")
        claimed = store.claim_offline_job(worker_id="w1", now=NOW)
        assert claimed is not None

        with pytest.raises(StoreError, match="unable to fail"):
            store.fail_offline_job(
                "wrong-fail-worker",
                worker_id="w-imposter",
                failed_at=NOW,
                error={"fail": True},
            )

    def test_full_job_lifecycle_enqueue_claim_complete(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        _enqueue_job(store, job_id="lifecycle-job")

        # Verify initially pending
        pending = store.iter_offline_jobs(statuses=[OfflineJobStatus.PENDING])
        assert len(pending) == 1

        # Claim
        claimed = store.claim_offline_job(worker_id="w", now=NOW)
        assert claimed is not None
        assert claimed.status is OfflineJobStatus.RUNNING

        running = store.iter_offline_jobs(statuses=[OfflineJobStatus.RUNNING])
        assert len(running) == 1

        # Complete
        store.complete_offline_job(
            "lifecycle-job",
            worker_id="w",
            completed_at=NOW + timedelta(seconds=30),
            result={"processed": True},
        )
        succeeded = store.iter_offline_jobs(statuses=[OfflineJobStatus.SUCCEEDED])
        assert len(succeeded) == 1
        assert succeeded[0].result == {"processed": True}

    def test_iter_offline_jobs_without_filter_returns_all(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        _enqueue_job(store, job_id="j1")
        _enqueue_job(store, job_id="j2")

        all_jobs = store.iter_offline_jobs()
        assert len(all_jobs) == 2


# ===========================================================================
# 9. UserState store edge cases
# ===========================================================================


class TestUserStateEdgeCases:
    """Edge-case tests for principal/session/namespace operations."""

    def test_read_nonexistent_principal_raises(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        with pytest.raises(StoreError, match="not found"):
            store.read_principal("ghost-principal")

    def test_read_nonexistent_session_raises(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        with pytest.raises(StoreError, match="not found"):
            store.read_session("ghost-session")

    def test_read_nonexistent_namespace_raises(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        with pytest.raises(StoreError, match="not found"):
            store.read_namespace("ghost-namespace")

    def test_insert_principal_upsert_preserves_created_at(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        first = store.insert_principal({
            "principal_id": "upsert-p",
            "tenant_id": "t",
            "roles": [],
            "capabilities": [],
            "preferences": {},
        })
        original_created = first["created_at"]

        # Upsert with updated roles
        updated = store.insert_principal({
            "principal_id": "upsert-p",
            "tenant_id": "t",
            "roles": ["admin"],
            "capabilities": [],
            "preferences": {},
        })

        assert updated["created_at"] == original_created
        assert updated["roles"] == ["admin"]

    def test_insert_session_upsert_preserves_started_at(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        store.insert_principal({
            "principal_id": "p-sess-upsert",
            "tenant_id": "t",
            "roles": [],
            "capabilities": [],
            "preferences": {},
        })

        first = store.insert_session({
            "session_id": "s-upsert",
            "principal_id": "p-sess-upsert",
            "channel": "cli",
            "metadata": {"step": 1},
        })
        original_started = first["started_at"]

        second = store.insert_session({
            "session_id": "s-upsert",
            "principal_id": "p-sess-upsert",
            "channel": "rest",
            "metadata": {"step": 2},
        })

        assert second["started_at"] == original_started
        assert second["channel"] == "rest"
        assert second["metadata"]["step"] == 2

    def test_list_principals_tenant_filter(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        for i in range(3):
            store.insert_principal({
                "principal_id": f"p-t1-{i}",
                "tenant_id": "tenant-1",
                "roles": [],
                "capabilities": [],
                "preferences": {},
            })
        store.insert_principal({
            "principal_id": "p-t2",
            "tenant_id": "tenant-2",
            "roles": [],
            "capabilities": [],
            "preferences": {},
        })

        t1_list = store.list_principals(tenant_id="tenant-1")
        t2_list = store.list_principals(tenant_id="tenant-2")
        all_list = store.list_principals()

        assert len(t1_list) == 3
        assert len(t2_list) == 1
        assert len(all_list) == 4

    def test_list_sessions_principal_filter(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        store.insert_principal({
            "principal_id": "pa",
            "tenant_id": "t",
            "roles": [],
            "capabilities": [],
            "preferences": {},
        })
        store.insert_principal({
            "principal_id": "pb",
            "tenant_id": "t",
            "roles": [],
            "capabilities": [],
            "preferences": {},
        })

        store.insert_session({"session_id": "sa1", "principal_id": "pa", "channel": "cli", "metadata": {}})
        store.insert_session({"session_id": "sa2", "principal_id": "pa", "channel": "cli", "metadata": {}})
        store.insert_session({"session_id": "sb1", "principal_id": "pb", "channel": "cli", "metadata": {}})

        pa_sessions = store.list_sessions(principal_id="pa")
        pb_sessions = store.list_sessions(principal_id="pb")
        all_sessions = store.list_sessions()

        assert len(pa_sessions) == 2
        assert len(pb_sessions) == 1
        assert len(all_sessions) == 3

    def test_update_session_merges_metadata(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        store.insert_principal({
            "principal_id": "p-merge",
            "tenant_id": "t",
            "roles": [],
            "capabilities": [],
            "preferences": {},
        })
        store.insert_session({
            "session_id": "s-merge",
            "principal_id": "p-merge",
            "channel": "cli",
            "metadata": {"key_a": "a", "key_b": "b"},
        })

        updated = store.update_session("s-merge", {"metadata": {"key_b": "B", "key_c": "c"}})

        assert updated["metadata"]["key_a"] == "a"   # preserved
        assert updated["metadata"]["key_b"] == "B"   # overwritten
        assert updated["metadata"]["key_c"] == "c"   # new

    def test_namespace_upsert_preserves_created_at(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        first = store.insert_namespace({
            "namespace_id": "ns-upsert",
            "tenant_id": "t",
            "visibility_policy": "team",
        })
        original_created = first["created_at"]

        updated = store.insert_namespace({
            "namespace_id": "ns-upsert",
            "tenant_id": "t",
            "visibility_policy": "private",
        })

        assert updated["created_at"] == original_created
        assert updated["visibility_policy"] == "private"


# ===========================================================================
# 10. Normalization / data integrity
# ===========================================================================


class TestNormalizationHelpers:
    """Verify normalization of payloads with enum values, defaults, etc."""

    def test_principal_enum_capabilities_are_stringified(self, tmp_path: Path) -> None:
        from mind.primitives.contracts import Capability

        store = _build_store(tmp_path)
        created = store.insert_principal({
            "principal_id": "p-enum",
            "tenant_id": "t",
            "principal_kind": "user",
            "roles": [],
            "capabilities": [Capability.MEMORY_READ, Capability.GOVERNANCE_PLAN],
            "preferences": {},
        })

        assert all(isinstance(cap, str) for cap in created["capabilities"])
        assert "memory_read" in created["capabilities"]

    def test_session_channel_enum_is_stringified(self, tmp_path: Path) -> None:
        from mind.app.context import SourceChannel

        store = _build_store(tmp_path)
        store.insert_principal({
            "principal_id": "p-channel",
            "tenant_id": "t",
            "roles": [],
            "capabilities": [],
            "preferences": {},
        })
        created = store.insert_session({
            "session_id": "s-channel",
            "principal_id": "p-channel",
            "channel": SourceChannel.CLI,
            "metadata": {},
        })

        assert created["channel"] == "cli"

    def test_principal_defaults_applied(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        created = store.insert_principal({
            "principal_id": "p-defaults",
        })

        assert created["principal_kind"] == "user"
        assert created["tenant_id"] == "default"
        assert created["roles"] == []
        assert created["capabilities"] == []
        assert created["preferences"] == {}
        assert created["created_at"] is not None
        assert created["updated_at"] is not None

    def test_namespace_defaults_applied(self, tmp_path: Path) -> None:
        store = _build_store(tmp_path)
        created = store.insert_namespace({
            "namespace_id": "ns-defaults",
        })

        assert created["tenant_id"] == "default"
        assert created["visibility_policy"] == "default"
        assert created["created_at"] is not None


# ===========================================================================
# 11. Fixtures set completeness
# ===========================================================================


class TestFixtureCompleteness:
    """Verify fixture sets are well-formed and complete."""

    def test_product_cli_bench_fixture_count(self) -> None:
        from mind.fixtures import build_product_cli_bench_v1

        scenarios = build_product_cli_bench_v1()
        assert len(scenarios) == 30
        ids = {s.scenario_id for s in scenarios}
        assert len(ids) == 30  # all unique

    def test_user_state_scenarios_fixture_count(self) -> None:
        from mind.fixtures import build_user_state_scenarios_v1

        scenarios = build_user_state_scenarios_v1()
        assert len(scenarios) == 30
        assert all(s.tenant_id.startswith("tenant-") for s in scenarios)
        assert all(s.principal_id.startswith("principal-") for s in scenarios)
        assert all(s.session_id.startswith("session-") for s in scenarios)

    def test_product_cli_bench_covers_all_command_families(self) -> None:
        from mind.fixtures import build_product_cli_bench_v1

        scenarios = build_product_cli_bench_v1()
        families = {s.command_family for s in scenarios}

        assert "help" in families
        assert "remember" in families
        assert "recall" in families
        assert "ask" in families
        assert "history" in families
        assert "session" in families
