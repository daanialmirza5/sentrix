"""FastAPI application factory."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import create_all, db_session, init_engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_engine()
    create_all()
    from .engines.deception import seed_honey
    with db_session() as db:
        seed_honey(db)
    if os.environ.get("SENTRIX_AUTO_SEED", "").lower() in {"1", "true", "yes"}:
        from .demo_seed import seed_if_empty
        with db_session() as db:
            seed_if_empty(db)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="SENTRIX", version="0.1.0", lifespan=lifespan,
                  description="Role-anchored identity drift detection for AI agents. Valid token != valid behavior.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "X-Agent-Secret"])

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > settings.max_request_bytes:
            return JSONResponse({"detail": "request body too large"}, status_code=413)
        return await call_next(request)

    from .api.routes import router
    app.include_router(router)
    _mount_ui(app)
    return app


def _mount_ui(app: FastAPI) -> None:
    """Production mode: serve the built console (frontend/dist) from the same origin as the API."""
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from .config import REPO_DIR
    dist = REPO_DIR / "frontend" / "dist"
    if not (dist / "index.html").exists():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(("v1/", "docs", "redoc", "openapi.json")):
            from fastapi import HTTPException
            raise HTTPException(404, "not found")
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


app = create_app()
