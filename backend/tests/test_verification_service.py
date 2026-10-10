import json
from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.models import Medicine, Patient, Verification
from app.schemas import VerificationCreateRequest
from app.services.verification_service import LIMITATIONS, verify_package


TODAY = date(2026, 10, 10)


@pytest.fixture
def verification_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Patient(id=1, demo_name="Demo Patient"))
        session.add(Medicine(
            brand_name="Demo Relief One",
            active_ingredient="Examplemol",
            strength="500 mg",
            dosage_form="tablet",
            route="oral",
            release_type="immediate",
            manufacturer="Demo Labs Alpha",
            registration_no="DEMO-001",
            data_source="demo_dataset",
        ))
        session.commit()
        yield session
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def reviewed_package(**overrides) -> VerificationCreateRequest:
    values = {
        "patient_id": 1,
        "brand_name": "Demo Relief One",
        "manufacturer": "Demo Labs Alpha",
        "registration_number": "DEMO-001",
        "batch_number": "BATCH-1",
        "expiry_date_text": "DEC 2030",
        "strength": "0.5 g",
        "dosage_form": "Tablet",
    }
    values.update(overrides)
    return VerificationCreateRequest(**values)


def finding_results(result) -> dict[str, str]:
    return {finding.field: finding.result for finding in result.findings}


def test_every_available_field_match_returns_record_match_and_saves(verification_session):
    result = verify_package(
        verification_session,
        reviewed_package(),
        today=TODAY,
    )

    assert result.verification.status == "record_match"
    assert finding_results(result) == {
        "brand_name": "match",
        "manufacturer": "match",
        "strength": "match",
        "dosage_form": "match",
        "expiry_date": "match",
    }
    assert "does not prove that a physical package is authentic" in LIMITATIONS

    stored = verification_session.exec(select(Verification)).one()
    assert stored.medicine_id == 1
    assert stored.source == "demo_dataset"
    assert json.loads(stored.extracted_details_json)["batch_number"] == "BATCH-1"
    assert len(json.loads(stored.findings_json)) == 5


def test_conflicting_field_returns_inconsistent_information(verification_session):
    result = verify_package(
        verification_session,
        reviewed_package(manufacturer="Different Manufacturer"),
        today=TODAY,
    )

    assert result.verification.status == "inconsistent_information"
    assert finding_results(result)["manufacturer"] == "mismatch"


def test_registration_number_lookup_takes_precedence_over_brand(verification_session):
    result = verify_package(
        verification_session,
        reviewed_package(brand_name="Demo Different Brand"),
        today=TODAY,
    )

    assert result.verification.medicine_id == 1
    assert result.verification.status == "inconsistent_information"
    assert finding_results(result)["brand_name"] == "mismatch"


def test_brand_lookup_is_used_when_registration_has_no_match(verification_session):
    result = verify_package(
        verification_session,
        reviewed_package(registration_number="UNKNOWN-001"),
        today=TODAY,
    )

    assert result.verification.medicine_id == 1
    assert result.verification.status == "record_match"


def test_no_catalog_record_returns_unable_to_verify(verification_session):
    result = verify_package(
        verification_session,
        reviewed_package(
            brand_name="Demo Unknown",
            registration_number="UNKNOWN-001",
        ),
        today=TODAY,
    )

    assert result.verification.status == "unable_to_verify"
    assert result.verification.medicine_id is None
    assert all(
        finding.result == "not_available"
        for finding in result.findings
        if finding.field != "expiry_date"
    )


def test_too_little_and_unparseable_data_returns_unable_to_verify(verification_session):
    result = verify_package(
        verification_session,
        reviewed_package(
            brand_name=None,
            manufacturer=None,
            strength=None,
            dosage_form=None,
            expiry_date_text="not readable",
        ),
        today=TODAY,
    )

    assert result.verification.status == "unable_to_verify"
    assert all(finding.result == "not_available" for finding in result.findings)


def test_expired_package_date_is_flagged_as_inconsistent(verification_session):
    result = verify_package(
        verification_session,
        reviewed_package(expiry_date_text="EXP 09/2026"),
        today=TODAY,
    )

    assert result.verification.status == "inconsistent_information"
    expiry = next(
        finding for finding in result.findings if finding.field == "expiry_date"
    )
    assert expiry.result == "mismatch"
    assert "in the past" in expiry.message
