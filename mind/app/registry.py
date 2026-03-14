"""Application service registry — single composition root."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from mind.access.service import AccessService
from mind.app.runtime import GlobalRuntimeManager
from mind.app.services.access import MemoryAccessService
from mind.app.services.feedback import FeedbackService
from mind.app.services.frontend import (
    FrontendDebugAppService,
    FrontendExperienceAppService,
    FrontendSettingsAppService,
)
from mind.app.services.governance import GovernanceAppService
from mind.app.services.ingest import MemoryIngestService
from mind.app.services.jobs import OfflineJobAppService
from mind.app.services.query import MemoryQueryService
from mind.app.services.system import SystemStatusService
from mind.app.services.user_state import UserStateService
from mind.capabilities import CapabilityService, resolve_capability_provider_config
from mind.cli_config import CliBackend, ResolvedCliConfig, resolve_cli_config
from mind.governance.service import GovernanceService
from mind.kernel.store import MemoryStore, SQLiteMemoryStore
from mind.offline.scheduler import OfflineJobScheduler
from mind.offline.service import OfflineMaintenanceService
from mind.primitives.service import PrimitiveService
from mind.telemetry import (
    CompositeTelemetryRecorder,
    TelemetryRecorder,
    build_dev_telemetry_recorder,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class AppServiceRegistry:
    """Holds all application-layer services and shared infrastructure."""

    store: MemoryStore = field(repr=False)
    config: ResolvedCliConfig = field(repr=False)
    telemetry_recorder: TelemetryRecorder | None = field(repr=False)
    capability_service: CapabilityService = field(repr=False)
    primitive_service: PrimitiveService = field(repr=False)
    access_service: AccessService = field(repr=False)
    governance_service: GovernanceService = field(repr=False)
    offline_service: OfflineMaintenanceService = field(repr=False)
    memory_ingest_service: MemoryIngestService = field(repr=False)
    memory_query_service: MemoryQueryService = field(repr=False)
    memory_access_service: MemoryAccessService = field(repr=False)
    governance_app_service: GovernanceAppService = field(repr=False)
    offline_job_app_service: OfflineJobAppService = field(repr=False)
    frontend_experience_service: FrontendExperienceAppService = field(repr=False)
    frontend_settings_service: FrontendSettingsAppService = field(repr=False)
    frontend_debug_service: FrontendDebugAppService = field(repr=False)
    user_state_service: UserStateService = field(repr=False)
    feedback_service: FeedbackService = field(repr=False)
    system_status_service: SystemStatusService = field(repr=False)
    runtime_manager: GlobalRuntimeManager = field(repr=False)

    @property
    def ingest_service(self) -> MemoryIngestService:
        return self.memory_ingest_service

    @property
    def query_service(self) -> MemoryQueryService:
        return self.memory_query_service

    @property
    def access_app_service(self) -> MemoryAccessService:
        return self.memory_access_service

    @property
    def job_service(self) -> OfflineJobAppService:
        return self.offline_job_app_service


@contextmanager
def build_app_registry(
    config: ResolvedCliConfig | None = None,
    *,
    telemetry_recorder: TelemetryRecorder | None = None,
    telemetry_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Iterator[AppServiceRegistry]:
    """Build a fully-wired ``AppServiceRegistry`` from config.

    Yields the registry as a context manager so resources (DB connections,
    etc.) can be cleaned up on exit.
    """

    if config is None:
        config = resolve_cli_config(allow_sqlite=False, env=env)

    # Build the store based on backend
    store: MemoryStore
    if config.backend is CliBackend.SQLITE:
        sqlite_path = config.sqlite_path or Path("artifacts/dev/mind.sqlite3")
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        store = SQLiteMemoryStore(str(sqlite_path))
    else:
        # PostgreSQL backend
        from mind.kernel.postgres_store import PostgresMemoryStore

        dsn = config.postgres_dsn
        if dsn is None:
            raise RuntimeError(
                "PostgreSQL DSN is required but not configured. "
                "Set MIND_POSTGRES_DSN or use --postgres-dsn."
            )
        store = PostgresMemoryStore(dsn)

    persistent_telemetry_recorder = build_dev_telemetry_recorder(
        telemetry_path=telemetry_path,
        env=env,
    )
    effective_telemetry_recorder: TelemetryRecorder | None
    if telemetry_recorder is not None and persistent_telemetry_recorder is not None:
        effective_telemetry_recorder = CompositeTelemetryRecorder(
            (telemetry_recorder, persistent_telemetry_recorder)
        )
    else:
        effective_telemetry_recorder = telemetry_recorder or persistent_telemetry_recorder

    user_state_service = UserStateService(store)
    system_status_service = SystemStatusService(store, config=config)
    runtime_manager = GlobalRuntimeManager(
        user_state_service=user_state_service,
        current_config=config,
        env=env,
    )
    runtime_manager.bootstrap()
    frontend_settings_service = FrontendSettingsAppService(
        system_status_service=system_status_service,
        user_state_service=user_state_service,
        current_config=config,
        runtime_manager=runtime_manager,
    )

    # Build domain services
    capability_service = CapabilityService(
        provider_config=resolve_capability_provider_config(
            selection=runtime_manager.current_provider_selection(),
            env=runtime_manager.current_provider_env(),
        ),
    )
    primitive_service = PrimitiveService(
        store,
        capability_service=capability_service,
        telemetry_recorder=effective_telemetry_recorder,
        provider_env_resolver=runtime_manager.current_provider_env,
    )
    access_service = AccessService(
        store,
        capability_service=capability_service,
        telemetry_recorder=effective_telemetry_recorder,
        provider_env_resolver=runtime_manager.current_provider_env,
    )
    governance_service = GovernanceService(store, telemetry_recorder=effective_telemetry_recorder)
    offline_service = OfflineMaintenanceService(
        store,
        capability_service=capability_service,
        telemetry_recorder=effective_telemetry_recorder,
        provider_env_resolver=runtime_manager.current_provider_env,
    )
    scheduler = OfflineJobScheduler(store)
    feedback_service = FeedbackService(
        primitive_service,
        request_defaults_resolver=runtime_manager.apply_request_defaults,
        scheduler=scheduler,
    )
    memory_ingest_service = MemoryIngestService(
        primitive_service,
        request_defaults_resolver=runtime_manager.apply_request_defaults,
        scheduler=scheduler,
    )
    memory_query_service = MemoryQueryService(
        primitive_service,
        store,
        request_defaults_resolver=runtime_manager.apply_request_defaults,
    )
    memory_access_service = MemoryAccessService(
        access_service,
        provider_env_resolver=runtime_manager.current_provider_env,
        request_defaults_resolver=runtime_manager.apply_request_defaults,
    )
    governance_app_service = GovernanceAppService(governance_service)
    offline_job_app_service = OfflineJobAppService(
        store,
        offline_service,
        request_defaults_resolver=runtime_manager.apply_request_defaults,
    )
    frontend_experience_service = FrontendExperienceAppService(
        memory_ingest_service=memory_ingest_service,
        memory_query_service=memory_query_service,
        memory_access_service=memory_access_service,
        offline_job_app_service=offline_job_app_service,
        request_defaults_resolver=runtime_manager.apply_request_defaults,
    )
    frontend_debug_service = FrontendDebugAppService(
        telemetry_source=(
            effective_telemetry_recorder  # type: ignore[arg-type]
            if hasattr(effective_telemetry_recorder, "iter_events")
            else None
        ),
        telemetry_path=telemetry_path,
        env=env,
        dev_mode_resolver=runtime_manager.current_dev_mode,
    )

    registry = AppServiceRegistry(
        store=store,
        config=config,
        telemetry_recorder=effective_telemetry_recorder,
        capability_service=capability_service,
        primitive_service=primitive_service,
        access_service=access_service,
        governance_service=governance_service,
        offline_service=offline_service,
        memory_ingest_service=memory_ingest_service,
        memory_query_service=memory_query_service,
        memory_access_service=memory_access_service,
        governance_app_service=governance_app_service,
        offline_job_app_service=offline_job_app_service,
        frontend_experience_service=frontend_experience_service,
        frontend_settings_service=frontend_settings_service,
        frontend_debug_service=frontend_debug_service,
        user_state_service=user_state_service,
        feedback_service=feedback_service,
        system_status_service=system_status_service,
        runtime_manager=runtime_manager,
    )

    try:
        yield registry
    finally:
        if hasattr(effective_telemetry_recorder, "close"):
            effective_telemetry_recorder.close()  # type: ignore[union-attr]
        # Cleanup if store has a close method
        if hasattr(store, "close"):
            store.close()
