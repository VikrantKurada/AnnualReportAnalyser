"""FastAPI app: JSON API under /api plus the built React SPA."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db as db_mod
from .api import admin, chat_api, companies, projects_api

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

BUILTIN_PERSONAS = [
    {"name": "CFO", "description": "Looks at the company as its Chief Financial Officer",
     "system_prompt": (
         "You are the Chief Financial Officer of the company being analysed. "
         "Focus on capital allocation, margins, cash flow, balance-sheet strength, "
         "cost discipline, and guidance credibility. Speak in first person about "
         "'our' company, be candid about weaknesses, and always ground statements "
         "in the reported numbers."),
     "builtin": 1},
    {"name": "Wall Street Analyst",
     "description": "A skeptical sell-side analyst covering the stock",
     "system_prompt": (
         "You are a skeptical Wall Street sell-side analyst covering this company. "
         "Focus on valuation drivers, growth durability, competitive moats, red "
         "flags in the filings, and how results compare to consensus expectations. "
         "Challenge management narratives and quantify claims wherever possible."),
     "builtin": 1},
]


def _seed(conn):
    existing = {r["name"] for r in conn.execute("SELECT name FROM personas")}
    for persona in BUILTIN_PERSONAS:
        if persona["name"] not in existing:
            db_mod.insert(conn, "personas", persona)


def create_app(db_path: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = db_mod.get_conn(app.state.db_path)
        db_mod.init_db(conn)
        _seed(conn)
        conn.close()
        yield

    app = FastAPI(title="Annual Report Analyser", lifespan=lifespan)
    app.state.db_path = db_path or str(db_mod.default_db_path())

    for router in (companies.router, chat_api.router, projects_api.router,
                   admin.router):
        app.include_router(router, prefix="/api")

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"),
                  name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = FRONTEND_DIST / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
