import os
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("nightpigeon.dashboard")

DASHBOARD_DIR = Path(__file__).parent / "dashboard"
API_URL = os.environ.get("API_URL", "").rstrip("/")


def create_dashboard_app() -> FastAPI:
    app = FastAPI(title="Nightpigeon Dashboard", docs_url=None, redoc_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/config.js")
    async def config_js():
        js = f"window.API_BASE = '{API_URL}';\n"
        return Response(content=js, media_type="application/javascript")

    app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")

    @app.get("/")
    async def root():
        return FileResponse(str(DASHBOARD_DIR / "index.html"))

    @app.get("/guilds")
    async def guilds_page():
        return FileResponse(str(DASHBOARD_DIR / "guilds.html"))

    @app.get("/config")
    async def config_page():
        return FileResponse(str(DASHBOARD_DIR / "config.html"))

    @app.get("/cases")
    async def cases_page():
        return FileResponse(str(DASHBOARD_DIR / "cases.html"))

    @app.get("/docs-page")
    async def docs_page():
        return FileResponse(str(DASHBOARD_DIR / "docs.html"))

    @app.get("/ping")
    async def ping():
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    log.info(f"Starting Nightpigeon dashboard on port {port} (API_URL={API_URL!r})")
    app = create_dashboard_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
