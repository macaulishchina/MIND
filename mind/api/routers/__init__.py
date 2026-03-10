"""REST router exports."""

from mind.api.routers.access import router as access_router
from mind.api.routers.governance import router as governance_router
from mind.api.routers.jobs import router as jobs_router
from mind.api.routers.memories import router as memories_router
from mind.api.routers.sessions import router as sessions_router
from mind.api.routers.system import router as system_router
from mind.api.routers.users import router as users_router

__all__ = [
    "access_router",
    "governance_router",
    "jobs_router",
    "memories_router",
    "sessions_router",
    "system_router",
    "users_router",
]
