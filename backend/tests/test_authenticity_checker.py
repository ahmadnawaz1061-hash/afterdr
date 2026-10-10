"""Tests for Pakistan Medicine Authenticity Checker and DRAP integration."""

from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.main import app
from app.models import Medicine, Patient
from app.schemas import VerificationCreateRequest
from app.services.authenticity import assess_authenticity, drap_provider, manufacturer_provider
from app.services.verification_service import verify_package


TODAY = date(2026, 10, 10)


@pytest.fixture
def auth_session():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        session.add(Patient(id=1, demo_name="Test Patient"))
        session.commit()
        yield session
    SQLModel.metadata.drop_all(test_engine)
    test_engine.dispose()


def test_registered_pakistan_product_returns_registered_unconfirmed():
    """Panadol 500mg matching DRAP Reg #005432 returns registered_unconfirmed outcome."""
    result = assess_authenticity(
        brand_name="Panadol",
        active_ingredient="Paracetamol",
        strength="500 mg",
        dosage_form="tablet",
        manufacturer="GlaxoSmithKline Pakistan Limited",
        registration_number="005432",
        batch_number="GSK-88192",
        mfg_date_text="JAN 2025",
        expiry_date_text="DEC 2028",
        today=TODAY,
    )

    assert result.outcome == "registered_unconfirmed"
    assert result.outcome_label == "Registered product found — package authenticity unconfirmed"
    assert not result.is_recalled
    assert not result.is_expired
    assert len(result.discrepancies) == 0
    assert any("DRAP Registration #005432" in e.detail for e in result.evidence)
    assert "cannot prove that a physical medicine is authentic" in result.disclaimer
    assert any("dra.gov.pk" in link["url"] for link in result.source_links)


def test_drap_recalled_batch_triggers_possible_recall():
    """Batch PK-AUG-991 from DRAP rapid alert returns possible_recall."""
    result = assess_authenticity(
        brand_name="Augmentin",
        manufacturer="GlaxoSmithKline Pakistan Limited",
        registration_number="012345",
        batch_number="PK-AUG-991",
        expiry_date_text="DEC 2028",
        today=TODAY,
    )

    assert result.outcome == "possible_recall"
    assert result.outcome_label == "Possible recall or safety alert"
    assert result.is_recalled is True
    assert any("DRAP-RAS-2024-001" in d for d in result.discrepancies)
    assert any("Do NOT consume" in step for step in result.recommended_next_steps)


def test_expired_medicine_is_flagged_with_expired_outcome():
    """Past expiry date returns expired outcome."""
    result = assess_authenticity(
        brand_name="Brufen",
        manufacturer="Abbott Laboratories (Pakistan) Limited",
        registration_number="000456",
        batch_number="AB-10293",
        expiry_date_text="MAY 2025",
        today=TODAY,
    )

    assert result.outcome == "expired"
    assert result.outcome_label == "Expired"
    assert result.is_expired is True
    assert any("has lapsed" in d for d in result.discrepancies)
    assert any("safely dispose" in step for step in result.recommended_next_steps)


def test_manufacturer_mismatch_against_drap_registry_flags_suspicious():
    """Registered DRAP product with unapproved/different manufacturer is flagged potentially_suspicious."""
    result = assess_authenticity(
        brand_name="Augmentin",
        manufacturer="Counterfeit Pharma Laboratory",
        registration_number="012345",
        batch_number="AUG-1122",
        expiry_date_text="DEC 2028",
        today=TODAY,
    )

    assert result.outcome == "potentially_suspicious"
    assert result.outcome_label == "Potentially suspicious"
    assert any("Manufacturer mismatch" in d for d in result.discrepancies)
    assert any("Do not take this medicine" in step for step in result.recommended_next_steps)


def test_visual_label_anomaly_flags_suspicious():
    """Altered label flags or broken tamper seal trigger potentially_suspicious."""
    result = assess_authenticity(
        brand_name="Panadol",
        registration_number="005432",
        batch_number="GSK-88192",
        expiry_date_text="DEC 2028",
        altered_label_flags=["Suspicious font size and misspelled active ingredient on carton"],
        visual_packaging_flags=["Tamper-evident holographic strip is peeling or broken"],
        today=TODAY,
    )

    assert result.outcome == "potentially_suspicious"
    assert any("Visual packaging alert" in d for d in result.discrepancies)


def test_future_manufacturing_date_flags_discrepancy():
    """Manufacturing date in the future is flagged as suspicious."""
    result = assess_authenticity(
        brand_name="Disprin",
        registration_number="001012",
        batch_number="RB-3344",
        mfg_date_text="NOV 2029",
        expiry_date_text="DEC 2030",
        today=TODAY,
    )

    assert result.outcome == "potentially_suspicious"
    assert any("Manufacturing date" in d and "in the future" in d for d in result.discrepancies)


def test_uncataloged_medicine_returns_inconclusive():
    """Medicine with unverified registration and uncataloged details returns inconclusive."""
    result = assess_authenticity(
        brand_name="Unknown Unregistered Drug",
        registration_number="UNREG-9999",
        batch_number="UNK-001",
        today=TODAY,
    )

    assert result.outcome == "inconclusive"
    assert result.outcome_label == "Inconclusive — more information needed"
    assert any("licensed pharmacist should review" in result.summary_message.lower() for _ in [1])


def test_authoritative_verification_outcome_when_live_manufacturer_confirms(monkeypatch):
    """When a live manufacturer service verifies the serial, outcome is verified_authoritative."""
    from app.services.authenticity.providers import ManufacturerVerificationResult

    def mock_verify(*args, **kwargs):
        return ManufacturerVerificationResult(
            verified=True,
            status="verified",
            manufacturer_name="GlaxoSmithKline Pakistan Limited",
            details="Live manufacturer serialization gateway confirmed unique packaging identifier.",
            is_live_service=True,
        )

    monkeypatch.setattr(manufacturer_provider, "verify_batch_or_serial", mock_verify)

    result = assess_authenticity(
        brand_name="Augmentin",
        manufacturer="GlaxoSmithKline Pakistan Limited",
        registration_number="012345",
        batch_number="GSK-VALID-01",
        expiry_date_text="DEC 2028",
        today=TODAY,
        mfg_service=manufacturer_provider,
    )

    assert result.outcome == "verified_authoritative"
    assert result.outcome_label == "Verified through an authoritative source"


def test_api_verification_endpoint_returns_rich_pakistan_authenticity_fields(auth_session):
    """POST /api/verifications endpoint returns rich authenticity fields."""
    with TestClient(app) as client:
        # Register and log in
        client.post("/api/auth/register", json={
            "name": "Authenticity Tester",
            "email": "authenticity@example.com",
            "password": "Password123!",
        })
        client.post("/api/auth/login", json={
            "email": "authenticity@example.com",
            "password": "Password123!",
        })

        response = client.post("/api/verifications", json={
            "brand_name": "Augmentin",
            "active_ingredient": "Amoxicillin + Clavulanic Acid",
            "manufacturer": "GlaxoSmithKline Pakistan Limited",
            "registration_number": "012345",
            "batch_number": "PK-AUG-991",
            "mfg_date_text": "JAN 2024",
            "expiry_date_text": "DEC 2028",
            "strength": "625 mg",
            "dosage_form": "tablet",
        })

        assert response.status_code == 201
        data = response.json()
        assert data["verification_id"] >= 1
        assert data["outcome"] == "possible_recall"
        assert data["outcome_label"] == "Possible recall or safety alert"
        assert len(data["discrepancies"]) > 0
        assert len(data["evidence"]) > 0
        assert len(data["recommended_next_steps"]) > 0
        assert len(data["source_links"]) > 0
        assert "physical package is authentic" in data["limitations"]
