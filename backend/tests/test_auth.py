from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.database import get_session
from app.main import app
from app.models import Account, Patient
from app.services.auth_service import get_current_user


def auth_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides.pop(get_current_user, None)
    return engine, TestClient(app)


def test_register_session_logout_and_login():
    engine, client = auth_client()
    try:
        registration = client.post("/api/auth/register", json={
            "name": "Ayesha Khan",
            "email": "Ayesha@Example.com",
            "password": "a-long-password-123",
        })
        assert registration.status_code == 201
        assert registration.json()["name"] == "Ayesha Khan"
        assert registration.json()["email"] == "ayesha@example.com"
        cookie = registration.headers["set-cookie"].casefold()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie

        current = client.get("/api/auth/me")
        assert current.status_code == 200
        assert current.json() == registration.json()

        with Session(engine) as session:
            account = session.exec(select(Account)).one()
            patient = session.get(Patient, account.patient_id)
            assert account.password_hash != "a-long-password-123"
            assert account.password_hash.startswith("$argon2")
            assert patient.demo_name == "Ayesha Khan"

        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401
        assert client.post("/api/auth/login", json={
            "email": "ayesha@example.com",
            "password": "wrong-password",
        }).status_code == 401

        login = client.post("/api/auth/login", json={
            "email": "ayesha@example.com",
            "password": "a-long-password-123",
        })
        assert login.status_code == 200
        assert client.get("/api/auth/me").status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_duplicate_email_and_protected_route():
    engine, client = auth_client()
    try:
        assert client.get("/api/dashboard").status_code == 401
        payload = {
            "name": "Ayesha Khan",
            "email": "ayesha@example.com",
            "password": "a-long-password-123",
        }
        assert client.post("/api/auth/register", json=payload).status_code == 201
        duplicate = client.post("/api/auth/register", json=payload)
        assert duplicate.status_code == 409
        assert "already exists" in duplicate.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
