
import os
from pathlib import Path

from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import init_db
from app.routers.api import router


load_dotenv(
    Path(__file__).resolve().parents[1] / ".env"
)


app = FastAPI(
    title="DeskSweep",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)


origins = [
    item.strip()
    for item in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if item.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(router)


@app.on_event("startup")
def startup():
    init_db()


static_dir = Path(__file__).resolve().parent / "static"

if static_dir.exists():

    assets_dir = static_dir / "assets"

    if assets_dir.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="assets"
        )

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):

        candidate = static_dir / full_path

        if full_path and candidate.is_file():
            return FileResponse(candidate)

        return FileResponse(static_dir / "index.html")
