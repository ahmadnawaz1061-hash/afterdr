from contextlib import asynccontextmanager
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app import models  # noqa: F401  # Registers SQLModel tables.
from app.database import create_db, engine
from app.routers import auth, dashboard, medicines, prescriptions, reports, schedules, verification
from app.schemas import HealthResponse
from app.seed import seed_database
from app.services.alternative_catalog import import_catalog
from app.services.packaging_upload_limit import PackagingUploadLimitMiddleware


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
DEFAULT_ALLOWED_ORIGINS = "http://localhost:5173"


def demo_seed_enabled() -> bool:
    return os.getenv("SEED_DEMO_DATA", "false").strip().casefold() in {
        "1", "true", "yes", "on",
    }


def configured_allowed_origins() -> list[str]:
    raw_origins = os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    origins = [origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip()]
    if not origins:
        raise RuntimeError("ALLOWED_ORIGINS must contain at least one frontend origin")
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError(
                "ALLOWED_ORIGINS must be a comma-separated list of HTTP(S) origins"
            )
    return list(dict.fromkeys(origins))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_db()
    if os.getenv("IMPORT_MEDICINE_CATALOG", "true").strip().casefold() in {"1", "true", "yes", "on"}:
        with Session(engine) as session:
            import_catalog(session)
    if demo_seed_enabled():
        with Session(engine) as session:
            seed_database(session=session)
    yield


app = FastAPI(title="After Dr API", lifespan=lifespan)
app.add_middleware(PackagingUploadLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(auth.router)
app.include_router(prescriptions.router)
app.include_router(schedules.router)
app.include_router(medicines.router)
app.include_router(verification.router)
app.include_router(reports.router)
app.include_router(dashboard.router)


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")
