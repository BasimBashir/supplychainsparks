"""Local FastAPI app: token-gated API + static dashboard."""
from __future__ import annotations

import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from sparks.config import Settings
from sparks.db import Database


def _server_token(db: Database) -> str:
    token = db.get_setting("server_token")
    if not token:
        token = secrets.token_urlsafe(24)
        db.set_setting("server_token", token)
    return token


def create_app(settings: Settings, db: Database | None = None,
               job_runner=None) -> FastAPI:
    db = db or Database(settings.db_path)
    token = _server_token(db)
    app = FastAPI(title="Supply Chain Sparks", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def check_token(request: Request, call_next):
        if request.url.path.startswith("/api"):
            if request.headers.get("X-Sparks-Token") != token:
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    from sparks.server.routes import router
    app.include_router(router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    app.state.settings = settings
    app.state.db = db
    if job_runner is None:
        from sparks.server.jobs import JobRunner
        job_runner = JobRunner()
    app.state.job_runner = job_runner

    dashboard_dist = settings.settings_path.parent / "dashboard" / "dist"
    if dashboard_dist.exists():
        app.mount("/", StaticFiles(directory=dashboard_dist, html=True), name="dashboard")
    return app
