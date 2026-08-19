from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.alerts import router as alerts_router
from app.api.preview_reports import router as preview_reports_router
from app.api.recommendations import router as recommendations_router
from app.api.stores import router as stores_router
from app.api.visibility import router as visibility_router
from app.core.config import get_settings
from app.core.db import engine

settings = get_settings()

app = FastAPI(title="Mersad — Store Visibility Growth Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(stores_router)
app.include_router(recommendations_router)
app.include_router(alerts_router)
app.include_router(visibility_router)
app.include_router(preview_reports_router)


@app.get("/health")
def health() -> dict:
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {"status": "ok" if db_ok else "degraded", "database": db_ok}
