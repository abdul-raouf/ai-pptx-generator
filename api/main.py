from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routers import jobs
from services.db import init_db
from pathlib import Path


init_db()


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


app = FastAPI()


app.include_router(jobs.router, prefix="/api/v1")
app.mount("/",  StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")