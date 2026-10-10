import json
from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.models import Medicine, Patient, Report, Verification
from app.schemas import ReportCreateRequest
from app.services.report_service import (
    DRAFT_LABEL,
    ReportNotFoundError,
    ReportVerificationNotFoundError,
    create_report_draft,
    generate_report_pdf,
)


@pytest.fixture
def report_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Patient(id=1, demo_name="Demo Patient"))
        medicine = Medicine(
            brand_name="Demo Relief One",
            active_ingredient="Examplemol",
            strength="500 mg",
            dosage_form="tablet",
            route="oral",
            manufacturer="Demo Labs Alpha",
            registration_no="DEMO-001",
        )
        session.add(medicine)
        session.flush()
        session.add(Verification(
            id=1,
            patient_id=1,
            medicine_id=medicine.id,
            extracted_details_json=json.dumps({
                "brand_name": "Demo Relief One",
                "manufacturer": "Different Manufacturer",
                "registration_number": "DEMO-001",
                "batch_number": "BATCH-1",
                "expiry_date_text": "DEC 2030",
            }),
            findings_json=json.dumps([{
                "field": "manufacturer",
                "result": "mismatch",
                "message": "Manufacturer differs from the reference record",
            }]),
            status="inconsistent_information",
            source="demo_dataset",
        ))
        session.commit()
        yield session
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def report_payload(**overrides) -> ReportCreateRequest:
    values = {
        "verification_id": 1,
        "pharmacy_name": "Demo Community Pharmacy",
        "purchase_date": date(2026, 10, 1),
        "description": "The visible manufacturer differs from the reference record.",
    }
    values.update(overrides)
    return ReportCreateRequest(**values)


def test_report_draft_is_saved_with_required_status(report_session):
    report = create_report_draft(report_session, report_payload())

    assert report.id == 1
    assert report.status == "draft_not_submitted"
    stored = report_session.exec(select(Report)).one()
    assert stored.pharmacy_name == "Demo Community Pharmacy"
    assert stored.description.startswith("The visible manufacturer")


def test_report_requires_an_existing_verification(report_session):
    with pytest.raises(ReportVerificationNotFoundError):
        create_report_draft(
            report_session,
            report_payload(verification_id=999999),
        )


def test_generated_pdf_contains_required_draft_and_evidence_content(report_session):
    report = create_report_draft(report_session, report_payload())
    pdf = generate_report_pdf(report_session, report.id)

    assert pdf.startswith(b"%PDF")
    assert DRAFT_LABEL == "DRAFT \u2014 NOT SUBMITTED"
    assert b"DRAFT \\227 NOT SUBMITTED" in pdf
    assert b"Manufacturer differs from the reference record" in pdf
    assert b"demo_dataset" in pdf
    assert b"does not prove that a physical package is authentic" in pdf
    assert b"https://www.dra.gov.pk/" in pdf
    assert b"Follow official regulatory instructions to submit." in pdf


def test_missing_report_cannot_be_downloaded(report_session):
    with pytest.raises(ReportNotFoundError):
        generate_report_pdf(report_session, 999999)
