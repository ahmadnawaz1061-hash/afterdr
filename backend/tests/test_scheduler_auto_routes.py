from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.database import get_session
from app.main import app
from app.models import Patient, Prescription, PrescriptionItem, ScheduleDose
from app.routers import prescriptions as prescriptions_router


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Patient(id=1, demo_name="Route Patient"))
        session.commit()

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as value:
        yield value, engine
    app.dependency_overrides.pop(get_session, None)
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def test_confirmation_returns_auto_schedule_and_needs_times(client):
    api, engine = client
    response = api.post("/api/prescriptions", json={
        "status": "confirmed",
        "auto_schedule": True,
        "medicines": [
            {"name": "Regular course", "frequency": "twice daily", "duration_days": 5, "needs_review": False},
            {"name": "Unclear course", "frequency": "with meals if required", "duration_days": 5, "needs_review": False},
        ],
    })

    assert response.status_code == 201
    items = response.json()["scheduling"]["items"]
    assert items[0]["status"] == "scheduled"
    assert items[0]["times"] == ["09:00", "21:00"]
    assert items[1]["status"] == "needs_times"
    assert items[1]["reason"]
    with Session(engine) as session:
        assert len(session.exec(select(ScheduleDose)).all()) > 0


def test_scheduling_failure_does_not_undo_saved_prescription(client, monkeypatch):
    api, engine = client

    def fail_after_save(*_args, **_kwargs):
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(prescriptions_router, "auto_schedule_prescription", fail_after_save)
    response = api.post("/api/prescriptions", json={
        "status": "confirmed", "auto_schedule": True,
        "medicines": [{"name": "Saved medicine", "frequency": "daily", "duration_days": 5, "needs_review": False}],
    })

    assert response.status_code == 201
    assert response.json()["scheduling"]["error"]
    with Session(engine) as session:
        prescription = session.get(Prescription, response.json()["prescription_id"])
        assert prescription is not None
        assert prescription.status == "confirmed"
        assert session.exec(select(PrescriptionItem)).one().medicine_name == "Saved medicine"


def test_schedule_view_and_regenerate_endpoint(client):
    api, _ = client
    saved = api.post("/api/prescriptions", json={
        "status": "confirmed", "auto_schedule": True,
        "medicines": [{"name": "Scheduled medicine", "dose": "1 tablet", "frequency": "daily", "duration_days": 5, "needs_review": False}],
    }).json()
    prescription_id = saved["prescription_id"]
    item_id = saved["scheduling"]["items"][0]["prescription_item_id"]

    schedule = api.get(f"/api/schedules?prescription_id={prescription_id}&timezone=Asia/Karachi")
    assert schedule.status_code == 200
    assert schedule.json()["items"][0]["medicine_name"] == "Scheduled medicine"
    assert schedule.json()["items"][0]["days"]

    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    future_time = tomorrow.astimezone().strftime("%H:%M")
    regenerated = api.post(
        f"/api/schedules/items/{item_id}/regenerate",
        json={"reminder_times": [future_time], "timezone": "Asia/Karachi"},
    )
    assert regenerated.status_code == 200
    assert regenerated.json()["status"] == "scheduled"


def test_regenerate_validates_item_state_and_times(client):
    api, engine = client
    with Session(engine) as session:
        prescription = Prescription(patient_id=1, status="needs_review")
        session.add(prescription)
        session.flush()
        item = PrescriptionItem(
            prescription_id=prescription.id, medicine_name="Not confirmed",
            duration_days=1, needs_review=False,
        )
        session.add(item)
        session.commit()
        item_id = item.id

    assert api.post(
        f"/api/schedules/items/{item_id}/regenerate",
        json={"reminder_times": ["09:00"], "timezone": "Asia/Karachi"},
    ).status_code == 409
    assert api.post(
        "/api/schedules/items/999999/regenerate",
        json={"reminder_times": ["09:00"], "timezone": "Asia/Karachi"},
    ).status_code == 404
    assert api.post(
        f"/api/schedules/items/{item_id}/regenerate",
        json={"reminder_times": [], "timezone": "Asia/Karachi"},
    ).status_code == 422
