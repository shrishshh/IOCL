from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import create_db_and_tables
from .routes.auth_routes import router as auth_router
from .routes.inspector import router as inspector_router
from .routes.zone_head import router as zh_router
from .routes.dept_officer import router as do_router

_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="IOCL Safety Risk Engine", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(inspector_router)
app.include_router(zh_router)
app.include_router(do_router)

# Serve PWA — must be last so API routes take priority
app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
