from collections.abc import Generator
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, Session, create_engine


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
DEFAULT_DATABASE_URL = "sqlite:///./medcare.db"


def configured_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL must not be empty")
    return database_url


def connection_args(database_url: str) -> dict[str, bool]:
    if database_url.startswith("sqlite:"):
        return {"check_same_thread": False}
    return {}


DATABASE_URL = configured_database_url()

engine = create_engine(
    DATABASE_URL,
    connect_args=connection_args(DATABASE_URL),
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Make declared SQLite foreign keys enforceable on every connection."""
    if dbapi_connection.__class__.__module__.split(".")[0] != "sqlite3":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db() -> None:
    # Importing models registers every table with SQLModel.metadata.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
