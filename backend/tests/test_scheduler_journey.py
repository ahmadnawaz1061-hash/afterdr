from datetime import datetime, timezone
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import models  # noqa: F401
from app.database import get_session
from app.main import app
from app.models import Patient
from app.services import schedule_service, dashboard_service


class MorningDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
        return value if tz is None else value.astimezone(tz)


def png_bytes():
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


def test_automatic_scheduler_journey_updates_dashboard(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Patient(id=1, demo_name="Journey Patient"))
        session.commit()

    def session_override():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(schedule_service, "datetime", MorningDateTime)
    monkeypatch.setattr(dashboard_service, "datetime", MorningDateTime)
    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            extraction = client.post(
                "/api/prescriptions/extract",
                files={"file": ("prescription.png", png_bytes(), "image/png")},
            )
            assert extraction.status_code == 200
            medicines = extraction.json()["medicines"]
            medicines[0].update({"frequency": "twice daily", "duration_days": 5, "needs_review": False})
            medicines[1].update({"frequency": "unclear", "duration_days": 5, "needs_review": False})

            confirmation = client.post("/api/prescriptions", json={
                "status": "confirmed", "auto_schedule": True, "medicines": medicines,
            })
            assert confirmation.status_code == 201
            scheduling = confirmation.json()["scheduling"]["items"]
            assert scheduling[0]["doses_created"] == 10
            assert scheduling[1]["status"] == "needs_times"

            prescription_id = confirmation.json()["prescription_id"]
            schedule = client.get(
                f"/api/schedules?prescription_id={prescription_id}&timezone=Asia/Karachi"
            )
            assert schedule.status_code == 200
            scheduled_item = schedule.json()["items"][0]
            assert sum(len(day["doses"]) for day in scheduled_item["days"]) == 10
            assert schedule.json()["items"][1]["status"] == "needs_times"

            first_dose = scheduled_item["days"][0]["doses"][0]
            marked = client.patch(
                f"/api/schedules/{first_dose['id']}", json={"status": "taken"}
            )
            assert marked.status_code == 200
            assert marked.json()["status"] == "taken"

            dashboard = client.get("/api/dashboard")
            assert dashboard.status_code == 200
            assert dashboard.json()["today"]["taken"] == 1
            assert dashboard.json()["today"]["remaining"] == 1
    finally:
        app.dependency_overrides.pop(get_session, None)
        SQLModel.metadata.drop_all(engine)
        engine.dispose()
