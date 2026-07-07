from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes.auth import router as auth_router
from app.api.routes.comments import router as comments_router
from app.api.routes.projects import router as projects_router
from app.api.routes.tasks import router as tasks_router
from app.core.config import get_settings
from app.core.errors import APIError, register_exception_handlers
from app.core.logging import setup_logging
from app.core.ratelimit import RateLimitMiddleware
from app.db.session import get_db
from app.middleware import RequestContextMiddleware

API_DESCRIPTION = """
A task/project management REST API built as a portfolio project focused on
production discipline.

**Auth flow:** `POST /auth/register`, then `POST /auth/login` returns a
short-lived access token (send it as `Authorization: Bearer <token>`) plus a
refresh token. When the access token expires, `POST /auth/refresh` rotates the
pair.

**Conventions**

- Task lists are cursor-paginated: responses include `next_cursor`; pass it back
  as `?cursor=` for the next page (`null` means the end).
- Every response carries an `X-Request-ID`, and every error uses one envelope:
  `{"error": {"code": ..., "message": ..., "request_id": ...}}`.
- Endpoints marked with a lock require a Bearer access token.
"""

TAGS_METADATA = [
    {"name": "auth", "description": "Register, log in, rotate/revoke tokens, current user."},
    {"name": "projects", "description": "Projects and their members. Owner-gated mutations."},
    {
        "name": "tasks",
        "description": "Assignment, validated status transitions, cursor-paginated lists.",
    },
    {"name": "comments", "description": "Comments on tasks."},
    {"name": "ops", "description": "Liveness and readiness probes."},
]


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        summary="Task/project management REST API with production-grade auth, "
        "pagination, and observability.",
        description=API_DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        contact={"name": "TaskFlow API", "url": "https://github.com/PvPles/taskflow-api"},
        license_info={
            "name": "MIT",
            "url": "https://github.com/PvPles/taskflow-api/blob/main/LICENSE",
        },
    )
    # Middleware runs outermost-last-added: RequestContext wraps RateLimit,
    # so 429s still get a request ID and an access-log line.
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(comments_router, prefix="/api/v1")

    @app.get("/health", tags=["ops"])
    def health():
        """Liveness: is the process up? Used by the ALB target group."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["ops"])
    def ready(db: Session = Depends(get_db)):
        """Readiness: can we actually serve traffic (database reachable)?"""
        try:
            db.execute(text("SELECT 1"))
        except Exception as exc:
            raise APIError(503, "not_ready", "Database is unreachable") from exc
        return {"status": "ready"}

    return app


app = create_app()
