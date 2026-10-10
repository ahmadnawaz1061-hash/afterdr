from datetime import datetime, time, timedelta, timezone
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from zoneinfo import ZoneInfo

from app.database import get_session
from app.main import app
from app.models import Medicine, Patient
from app.routers import prescriptions as prescriptions_router
from app.routers import verification as verification_router
from app.services.gemini_service import (
    GeminiAccessError,
    GeminiTimeoutError,
    MedicineExtraction,
    PrescriptionExtraction,
)


EXPECTED_OPERATIONS = {
    ("get", "/api/health"),
    ("post", "/api/auth/register"),
    ("post", "/api/auth/login"),
    ("post", "/api/auth/logout"),
    ("get", "/api/auth/me"),
    ("post", "/api/prescriptions/extract"),
    ("post", "/api/prescriptions"),
    ("get", "/api/prescriptions/{prescription_id}"),
    ("post", "/api/schedules"),
    ("get", "/api/schedules/today"),
    ("patch", "/api/schedules/{dose_id}"),
    ("get", "/api/medicines/search"),
    ("get", "/api/medicines/{medicine_id}/alternatives"),
    ("post", "/api/verifications/extract"),
    ("post", "/api/verifications"),
    ("post", "/api/reports"),
    ("get", "/api/reports/{report_id}/download"),
    ("get", "/api/dashboard"),
}


@pytest.fixture(autouse=True)
def isolated_api_database():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        session.add(Patient(id=1, demo_name="Demo Patient"))
        session.add_all([
            Medicine(
                brand_name="Demo Relief One",
                active_ingredient="Examplemol",
                strength="500 mg",
                dosage_form="tablet",
                route="oral",
                manufacturer="Demo Labs Alpha",
                registration_no="DEMO-001",
            ),
            Medicine(
                brand_name="Demo Relief Two",
                active_ingredient="Examplemol",
                strength="0.5 g",
                dosage_form="tablet",
                route="oral",
                manufacturer="Demo Labs Beta",
                registration_no="DEMO-002",
            ),
            Medicine(
                brand_name="Demo Calm One",
                active_ingredient="Mockadine",
                strength="10 mg",
                dosage_form="capsule",
                route="oral",
            ),
        ])
        session.commit()

    def override_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    yield test_engine
    app.dependency_overrides.clear()
    SQLModel.metadata.drop_all(test_engine)
    test_engine.dispose()


def image_bytes(format_name: str) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (20, 20), color="white").save(buffer, format=format_name)
    return buffer.getvalue()


def test_every_phase_3_route_appears_in_openapi():
    schema = app.openapi()
    operations = {
        (method, path)
        for path, path_item in schema["paths"].items()
        for method in path_item
        if method in {"get", "post", "patch"}
    }
    assert operations == EXPECTED_OPERATIONS
    assert schema["paths"]["/api/reports/{report_id}/download"]["get"]["responses"]["200"]["content"]["application/pdf"]["schema"]["format"] == "binary"

    with TestClient(app) as client:
        docs = client.get("/docs")
    assert docs.status_code == 200
    assert "Swagger UI" in docs.text


def test_prescription_routes_return_frontend_contract_shapes():
    with TestClient(app) as client:
        extraction = client.post(
            "/api/prescriptions/extract",
            files={"file": ("demo.png", image_bytes("PNG"), "image/png")},
        )
        assert extraction.status_code == 200
        assert extraction.json() == {
            "status": "needs_review",
            "patient_name": "Synthetic Demo Patient",
            "doctor_name": "Synthetic Demo Prescriber",
            "is_demo": True,
            "medicines": [
                {
                    "name": "Synthetic Demo Medicine A", "strength": "500 mg", "dose": "1 tablet",
                    "frequency": "Twice daily", "duration_days": 5, "instructions": "After food",
                    "needs_review": False, "is_demo": True,
                },
                {
                    "name": "Synthetic Demo Medicine B", "strength": None, "dose": "1 capsule",
                    "frequency": "Once daily", "duration_days": 3, "instructions": None,
                    "needs_review": True, "is_demo": True,
                },
            ],
            "simulated": True,
        }

        not_saved = client.get("/api/prescriptions/1")
        assert not_saved.status_code == 404

        saved = client.post("/api/prescriptions", json={
            "patient_id": 1,
            "status": "confirmed",
            "medicines": extraction.json()["medicines"],
        })
        assert saved.status_code == 201
        assert saved.json() == {"prescription_id": 1, "status": "confirmed", "medicine_count": 2}

        detail = client.get("/api/prescriptions/1")
        assert detail.status_code == 200
        assert detail.json()["prescription_id"] == 1
        assert len(detail.json()["medicines"]) == 2
        assert all(
            medicine["prescription_item_id"] > 0
            for medicine in detail.json()["medicines"]
        )


def test_extract_is_not_parsed_as_a_prescription_id():
    with TestClient(app) as client:
        response = client.get("/api/prescriptions/extract")
        invalid_id = client.get("/api/prescriptions/not-an-id")

    assert response.status_code == 405
    assert "int_parsing" not in response.text
    assert invalid_id.status_code == 404


def test_real_extraction_route_calls_service_and_removes_demo_flags(monkeypatch):
    captured = {}

    def extraction_service(image):
        captured["image"] = image
        return PrescriptionExtraction(
            patient_name="Visible Patient",
            doctor_name=None,
            medicines=[MedicineExtraction(
                name="Visible Medicine",
                strength="25 mg",
                needs_review=True,
            )],
        ), False

    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.setattr(
        prescriptions_router,
        "extract_prescription_draft",
        extraction_service,
    )

    upload = image_bytes("PNG")
    with TestClient(app) as client:
        response = client.post(
            "/api/prescriptions/extract",
            files={"file": ("prescription.png", upload, "application/octet-stream")},
        )

    assert response.status_code == 200
    assert captured == {"image": upload}
    assert response.json()["simulated"] is False
    assert response.json()["is_demo"] is False
    assert response.json()["medicines"][0]["is_demo"] is False


def test_gemini_access_failure_returns_safe_actionable_detail(monkeypatch):
    def denied_service(_image):
        raise GeminiAccessError("provider detail must stay private")

    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.setattr(
        prescriptions_router,
        "extract_prescription_draft",
        denied_service,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/prescriptions/extract",
            files={"file": ("prescription.png", image_bytes("PNG"), "image/png")},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": GeminiAccessError.public_message}
    assert "provider detail" not in response.text


def test_prescription_upload_validation_has_distinct_errors():
    with TestClient(app) as client:
        invalid = client.post(
            "/api/prescriptions/extract",
            files={"file": ("not-an-image.png", b"not an image", "image/png")},
        )
        oversized = client.post(
            "/api/prescriptions/extract",
            files={
                "file": (
                    "oversized.png",
                    b"x" * (5 * 1024 * 1024 + 1),
                    "image/png",
                )
            },
        )

    assert invalid.status_code == 400
    assert invalid.json() == {"detail": "Invalid or corrupt PNG/JPEG image"}
    assert oversized.status_code == 413
    assert oversized.json() == {"detail": "Image exceeds the 5 MB limit"}


def test_package_upload_validation_has_distinct_errors():
    with TestClient(app) as client:
        invalid = client.post(
            "/api/verifications/extract",
            files={"file": ("not-an-image.png", b"not an image", "image/png")},
        )
        oversized = client.post(
            "/api/verifications/extract",
            files={
                "file": (
                    "oversized.jpg",
                    b"x" * (5 * 1024 * 1024 + 1),
                    "image/jpeg",
                )
            },
        )

    assert invalid.status_code == 400
    assert invalid.json() == {"detail": "Invalid or corrupt PNG/JPEG image"}
    assert oversized.status_code == 413
    assert oversized.json() == {"detail": "Image exceeds the 5 MB limit"}


def test_package_provider_failure_returns_safe_gateway_error(monkeypatch):
    def timed_out_service(_image):
        raise GeminiTimeoutError("provider detail must stay private")

    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.setattr(
        verification_router,
        "extract_package_draft",
        timed_out_service,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/verifications/extract",
            files={"file": ("package.png", image_bytes("PNG"), "image/png")},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": GeminiTimeoutError.public_message}
    assert "provider detail" not in response.text


def test_schedule_routes_return_frontend_contract_shapes():
    with TestClient(app) as client:
        saved = client.post("/api/prescriptions", json={
            "patient_id": 1,
            "status": "confirmed",
            "medicines": [{"name": "Demo Relief One", "needs_review": False}],
        })
        prescription_id = saved.json()["prescription_id"]
        detail = client.get(f"/api/prescriptions/{prescription_id}").json()
        item_id = detail["medicines"][0]["prescription_item_id"]
        local_today = datetime.now(timezone.utc).astimezone(
            ZoneInfo("Asia/Karachi")
        ).date()
        schedule_payload = {
            "prescription_item_id": item_id,
            "start_date": str(local_today),
            "duration_days": 5,
            "reminder_times": ["09:00", "21:00"],
            "timezone": "Asia/Karachi",
        }
        created = client.post("/api/schedules", json={
            **schedule_payload,
        })
        assert created.status_code == 201
        assert created.json() == {
            "schedule_id": item_id,
            "doses_created": 10,
            "status": "scheduled",
        }

        repeated = client.post("/api/schedules", json=schedule_payload)
        assert repeated.status_code == 201
        assert repeated.json()["doses_created"] == 0

        today = client.get("/api/schedules/today")
        assert today.status_code == 200
        assert len(today.json()) == 2
        assert [dose["local_time"] for dose in today.json()] == ["09:00", "21:00"]
        assert all(dose["medicine_name"] == "Demo Relief One" for dose in today.json())
        now_local = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Karachi"))
        expected_statuses = [
            "missed" if now_local > datetime.combine(
                local_today,
                time.fromisoformat(reminder_time),
                tzinfo=ZoneInfo("Asia/Karachi"),
            ) + timedelta(minutes=30) else "pending"
            for reminder_time in ["09:00", "21:00"]
        ]
        assert [dose["status"] for dose in today.json()] == expected_statuses

        dose_id = today.json()[0]["id"]
        updated = client.patch(f"/api/schedules/{dose_id}", json={"status": "taken"})
        assert updated.status_code == 200
        assert updated.json()["id"] == dose_id
        assert updated.json()["status"] == "taken"
        assert updated.json()["taken_at"] is not None

        missed = client.patch(f"/api/schedules/{dose_id}", json={"status": "missed"})
        assert missed.json()["status"] == "missed"
        assert missed.json()["taken_at"] is None

        pending = client.patch(f"/api/schedules/{dose_id}", json={"status": "pending"})
        assert pending.json()["status"] == "pending"
        assert pending.json()["taken_at"] is None


def test_medicine_routes_use_catalog_matching_and_limit_search(isolated_api_database):
    with TestClient(app) as client:
        catalog = client.get("/api/medicines/search", params={"q": ""})
        assert catalog.status_code == 200
        assert len(catalog.json()) == 3
        assert set(catalog.json()[0]) == {
            "id", "brand_name", "active_ingredient", "strength", "dosage_form", "route",
            "release_type", "manufacturer", "registration_no", "data_source", "is_demo",
        }
        assert [item["id"] for item in client.get("/api/medicines/search", params={"q": "exampleMOL"}).json()] == [1, 2]
        assert client.get("/api/medicines/search", params={"q": "no such medicine"}).json() == []

        alternatives = client.get("/api/medicines/1/alternatives")
        assert alternatives.status_code == 200
        assert alternatives.json()[0]["id"] == 2
        assert alternatives.json()[0]["is_alternative"] is True
        assert alternatives.json()[0]["match_reasons"] == [
            "Same active ingredient(s)",
            "Equivalent normalized strength",
            "Same dosage form",
            "Same route",
            "Same release type",
        ]
        assert alternatives.json()[0]["notice"] == (
            "Confirm with your pharmacist or prescriber before substituting."
        )
        assert client.get("/api/medicines/999999/alternatives").status_code == 404

    with Session(isolated_api_database) as session:
        session.add_all([
            Medicine(
                brand_name=f"Demo Search {index:02d}",
                active_ingredient="Searchmol",
                strength="1 mg",
                dosage_form="tablet",
                route="oral",
            )
            for index in range(12)
        ])
        session.commit()

    with TestClient(app) as client:
        limited = client.get("/api/medicines/search", params={"q": "Searchmol"})
    assert limited.status_code == 200
    assert len(limited.json()) == 10


def test_verification_routes_return_frontend_contract_shapes():
    with TestClient(app) as client:
        extraction = client.post(
            "/api/verifications/extract",
            files={"file": ("package.jpg", image_bytes("JPEG"), "image/jpeg")},
        )
        assert extraction.status_code == 200
        assert extraction.json() == {
            "brand_name": "Synthetic Demo Package Medicine",
            "manufacturer": "Synthetic Demo Manufacturer",
            "registration_number": None,
            "batch_number": "SYNTH-DEMO-001",
            "expiry_date_text": "DEC 2030",
            "strength": "500 mg",
            "dosage_form": "tablet",
            "needs_review": True,
            "is_demo": True,
            "simulated": True,
        }

        result = client.post("/api/verifications", json={
            "patient_id": 1,
            "brand_name": "Demo Relief One",
            "manufacturer": "Different Manufacturer",
            "registration_number": "DEMO-001",
            "batch_number": "BATCH-1",
            "expiry_date_text": "DEC 2030",
            "strength": "0.5 g",
            "dosage_form": "tablet",
        })
        assert result.status_code == 201
        body = result.json()
        assert body["verification_id"] == 1
        assert body["status"] == "inconsistent_information"
        assert body["counterfeit_confirmed"] is False
        assert body["source"] == "demo_dataset"
        assert body["is_demo"] is True
        assert "does not prove that a physical package is authentic" in body["limitations"]
        assert {finding["field"]: finding["result"] for finding in body["findings"]} == {
            "brand_name": "match",
            "manufacturer": "mismatch",
            "strength": "match",
            "dosage_form": "match",
            "expiry_date": "match",
        }


def test_report_dashboard_and_health_routes_return_data():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}

        verification = client.post("/api/verifications", json={
            "patient_id": 1,
            "brand_name": "Demo Relief One",
            "manufacturer": "Different Manufacturer",
            "registration_number": "DEMO-001",
            "batch_number": "BATCH-1",
            "expiry_date_text": "DEC 2030",
            "strength": "500 mg",
            "dosage_form": "tablet",
        })
        verification_id = verification.json()["verification_id"]
        report = client.post("/api/reports", json={
            "verification_id": verification_id,
            "pharmacy_name": "Demo Community Pharmacy",
            "purchase_date": "2026-10-01",
            "description": "The manufacturer differs from the reference record.",
        })
        assert report.status_code == 201
        assert report.json() == {
            "report_id": 1,
            "status": "draft_not_submitted",
        }

        download = client.get("/api/reports/1/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/pdf"
        assert download.content.startswith(b"%PDF")
        assert b"DRAFT \\227 NOT SUBMITTED" in download.content
        assert "medcare-report-1-draft.pdf" in download.headers["content-disposition"]
        assert client.get("/api/reports/999999/download").status_code == 404
        assert client.post("/api/reports", json={
            "verification_id": 999999,
            "pharmacy_name": "Demo Pharmacy",
            "description": "Visible packaging concern.",
        }).status_code == 404

        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json() == {
            "patient": {"id": 1, "name": "Demo Patient"},
            "active_prescriptions": 0,
            "today": {"total_doses": 0, "taken": 0, "missed": 0, "remaining": 0},
            "next_dose": None,
            "recent_verifications": 1,
        }


def test_request_validation_is_visible_in_docs_and_enforced():
    with TestClient(app) as client:
        assert client.get("/api/prescriptions/0").status_code == 422
        assert client.get("/api/prescriptions/-1").status_code == 404
        assert client.get("/api/medicines/0/alternatives").status_code == 422
        assert client.patch("/api/schedules/0", json={"status": "pending"}).status_code == 422
        assert client.get("/api/reports/0/download").status_code == 422
        assert client.patch("/api/schedules/301", json={"status": "completed"}).status_code == 422
        schedule_payload = {
            "prescription_item_id": 999999,
            "start_date": "2026-10-10",
            "duration_days": 5,
            "reminder_times": ["09:00"],
            "timezone": "Asia/Karachi",
        }
        assert client.post("/api/schedules", json=schedule_payload).status_code == 404
        assert client.post("/api/schedules", json={
            key: value
            for key, value in schedule_payload.items()
            if key != "prescription_item_id"
        }).status_code == 422
        assert client.post("/api/schedules", json={
            **schedule_payload,
            "reminder_times": [],
        }).status_code == 422
        assert client.post("/api/schedules", json={
            **schedule_payload,
            "reminder_times": ["25:00"],
        }).status_code == 422
        assert client.post("/api/prescriptions", json={"status": "confirmed", "medicines": []}).status_code == 422
        assert client.post("/api/prescriptions", json={
            "status": "confirmed",
            "medicines": [{"name": "   "}],
        }).status_code == 422
        assert client.post("/api/verifications", json={"unexpected": True}).status_code == 422
        assert client.post("/api/verifications", json={
            "medicine_id": 999999,
        }).status_code == 404
        assert client.post("/api/reports", json={
            "verification_id": 1,
            "description": "Visible packaging concern.",
        }).status_code == 422
        assert client.post("/api/reports", json={
            "verification_id": 1,
            "pharmacy_name": "   ",
            "description": "   ",
        }).status_code == 422


def test_missing_prescription_returns_404():
    with TestClient(app) as client:
        response = client.get("/api/prescriptions/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Prescription 999999 was not found"}
