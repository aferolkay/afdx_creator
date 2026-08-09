"""FastAPI application."""

from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import generate, projects
from .storage.paths import html_template_dir, static_dir

_STATIC_URL = re.compile(r'(src|href)="(/static/[^"?]+)"')


def _with_cache_busting(html: str) -> str:
    """Stamp every /static/ URL with the file's modification time.

    Without this, a browser happily keeps serving the JavaScript it cached earlier and the page
    silently runs old code -- which is indistinguishable from a feature not having been built.
    A changed file changes its URL, so the browser has no choice but to fetch it.
    """
    root = static_dir()

    def stamp(match: re.Match) -> str:
        attribute, url = match.group(1), match.group(2)
        path = root / url[len("/static/"):]
        try:
            version = int(path.stat().st_mtime)
        except OSError:
            return match.group(0)  # unknown file: leave it exactly as written
        return f'{attribute}="{url}?v={version}"'

    return _STATIC_URL.sub(stamp, html)


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
        html = (html_template_dir() / "index.html").read_text(encoding="utf-8")
        # The page itself must never be cached, or the browser keeps the old asset URLs and the
        # cache-busting below has nothing to act on.
        return HTMLResponse(
            _with_cache_busting(html),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    return app


app = create_app()
