"""FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import generate, projects
from .storage.paths import html_template_dir, static_dir


def create_app() -> FastAPI:
    app = FastAPI(title="afdx_generator", version="0.1.0")

    app.include_router(projects.router)
    app.include_router(generate.router)

    app.mount("/static", StaticFiles(directory=static_dir()), name="static")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (html_template_dir() / "index.html").read_text(encoding="utf-8")

    return app


app = create_app()
