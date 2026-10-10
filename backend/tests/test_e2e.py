"""Complete API journey using deterministic mock image extraction."""

from datetime import datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.database import get_session
from app.main import app
from app.models import Medicine, Patient


@pytest.fixture
def e2e_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Patient(id=1, demo_name="Demo Patient"))
        session.add_all([
            Medicine(
                brand_name="Demo Relief One",
                active_ingredient="Examplemol",
                strength="500 mg",
                dosage_form="tablet",
                route="oral",
                release_type="immediate",
                manufacturer="Demo Labs Alpha",
                registration_no="DEMO-001",
                data_source="demo_dataset",
            ),
            Medicine(
                brand_name="Demo Relief Two",
                active_ingredient="Examplemol",
                strength="0.5 g",
                dosage_form="tablet",
                route="oral",
                release_type="immediate",
                manufacturer="Demo Labs Beta",
                registration_no="DEMO-002",
                data_source="demo_dataset",
            ),
        ])
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (24, 24), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_complete_mock_ai_journey(e2e_client):
    prescription_extraction = e2e_client.post(
        "/api/prescriptions/extract",
        files={"file": ("prescription.png", png_bytes(), "image/png")},
    )
    assert prescription_extraction.status_code == 200
    extracted_prescription = prescription_extraction.json()
    assert extracted_prescription["status"] == "needs_review"
    assert extracted_prescription["simulated"] is True
    assert len(extracted_prescription["medicines"]) == 2

    reviewed_medicines = [
        {**medicine, "needs_review": False}
        for medicine in extracted_prescription["medicines"]
    ]
    reviewed_medicines[0]["name"] = "Demo Relief One"
    reviewed_medicines[0]["strength"] = "500 mg"
    confirmation = e2e_client.post("/api/prescriptions", json={
        "patient_id": 1,
        "status": "confirmed",
        "medicines": reviewed_medicines,
    })
    assert confirmation.status_code == 201
    prescription_id = confirmation.json()["prescription_id"]

    prescription = e2e_client.get(f"/api/prescriptions/{prescription_id}")
    assert prescription.status_code == 200
    saved_medicine = prescription.json()["medicines"][0]
    prescription_item_id = saved_medicine["prescription_item_id"]
    prescribed_medicine_id = saved_medicine["medicine_id"]
    assert prescription_item_id > 0
    assert prescribed_medicine_id > 0

    local_today = datetime.now(timezone.utc).astimezone(
        ZoneInfo("Asia/Karachi")
    ).date()
    schedule = e2e_client.post("/api/schedules", json={
        "prescription_item_id": prescription_item_id,
        "start_date": local_today.isoformat(),
        "duration_days": 1,
        "reminder_times": ["00:01", "23:59"],
        "timezone": "Asia/Karachi",
    })
    assert schedule.status_code == 201
    assert schedule.json()["doses_created"] == 2

    today = e2e_client.get(
        "/api/schedules/today",
        params={"timezone": "Asia/Karachi"},
    )
    assert today.status_code == 200
    assert len(today.json()) == 2
    dose_id = today.json()[0]["id"]

    taken = e2e_client.patch(
        f"/api/schedules/{dose_id}",
        json={"status": "taken"},
    )
    assert taken.status_code == 200
    assert taken.json()["status"] == "taken"
    assert taken.json()["taken_at"] is not None

    dashboard = e2e_client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["active_prescriptions"] == 1
    assert dashboard.json()["today"] == {
        "total_doses": 2,
        "taken": 1,
        "missed": 0,
        "remaining": 1,
    }
    assert dashboard.json()["next_dose"] == {
        "medicine": "Demo Relief One",
        "time": "23:59",
    }
    assert dashboard.json()["recent_verifications"] == 0

    missed = e2e_client.patch(
        f"/api/schedules/{today.json()[1]['id']}",
        json={"status": "missed"},
    )
    assert missed.status_code == 200
    refreshed_dashboard = e2e_client.get("/api/dashboard")
    assert refreshed_dashboard.status_code == 200
    assert refreshed_dashboard.json()["today"] == {
        "total_doses": 2,
        "taken": 1,
        "missed": 1,
        "remaining": 0,
    }
    assert refreshed_dashboard.json()["next_dose"] is None

    search = e2e_client.get(
        "/api/medicines/search",
        params={"q": "Demo Relief One"},
    )
    assert search.status_code == 200
    original_medicine_id = search.json()[0]["id"]
    assert original_medicine_id == prescribed_medicine_id
    alternatives = e2e_client.get(
        f"/api/medicines/{original_medicine_id}/alternatives"
    )
    assert alternatives.status_code == 200
    assert [candidate["brand_name"] for candidate in alternatives.json()] == [
        "Demo Relief Two"
    ]
    assert alternatives.json()[0]["notice"] == (
        "Confirm with your pharmacist or prescriber before substituting."
    )

    package_extraction = e2e_client.post(
        "/api/verifications/extract",
        files={"file": ("package.png", png_bytes(), "image/png")},
    )
    assert package_extraction.status_code == 200
    extracted_package = package_extraction.json()
    assert extracted_package["needs_review"] is True
    assert extracted_package["simulated"] is True

    verification = e2e_client.post("/api/verifications", json={
        "patient_id": 1,
        "brand_name": "Demo Relief One",
        "manufacturer": "Different Manufacturer",
        "registration_number": "DEMO-001",
        "batch_number": extracted_package["batch_number"],
        "expiry_date_text": extracted_package["expiry_date_text"],
        "strength": "500 mg",
        "dosage_form": "tablet",
    })
    assert verification.status_code == 201
    verification_body = verification.json()
    assert verification_body["status"] == "inconsistent_information"
    assert verification_body["counterfeit_confirmed"] is False
    assert any(
        finding["field"] == "manufacturer" and finding["result"] == "mismatch"
        for finding in verification_body["findings"]
    )
    verification_id = verification_body["verification_id"]

    report = e2e_client.post("/api/reports", json={
        "verification_id": verification_id,
        "pharmacy_name": "Demo Community Pharmacy",
        "purchase_date": local_today.isoformat(),
        "description": "The visible manufacturer differs from the reference record.",
    })
    assert report.status_code == 201
    assert report.json()["status"] == "draft_not_submitted"
    report_id = report.json()["report_id"]

    download = e2e_client.get(f"/api/reports/{report_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.content.startswith(b"%PDF")
    assert b"DRAFT \\227 NOT SUBMITTED" in download.content

    final_dashboard = e2e_client.get("/api/dashboard")
    assert final_dashboard.status_code == 200
    assert final_dashboard.json()["recent_verifications"] == 1
