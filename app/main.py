from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.comments import router as comments_router
from app.api.routes.projects import router as projects_router
from app.api.routes.tasks import router as tasks_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.ratelimit import RateLimitMiddleware
from app.middleware import RequestContextMiddleware


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        description="Task/project management REST API.",
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
        return {"status": "ok"}

    return app


app = create_app()
