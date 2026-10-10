from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.models import Patient, Prescription, PrescriptionItem, ScheduleDose, Verification
from app.services.dashboard_service import (
    DashboardPatientNotFoundError,
    get_dashboard_snapshot,
)


NOW = datetime(2026, 10, 10, 5, 0, tzinfo=timezone.utc)


@pytest.fixture
def dashboard_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def add_verification(session: Session, patient_id: int) -> None:
    session.add(Verification(
        patient_id=patient_id,
        medicine_id=None,
        extracted_details_json="{}",
        findings_json="[]",
        status="unable_to_verify",
        source="demo_dataset",
    ))


def test_dashboard_aggregates_only_the_demo_patient_and_local_day(dashboard_session):
    dashboard_session.add_all([
        Patient(id=1, demo_name="Demo Patient"),
        Patient(id=2, demo_name="Other Patient"),
    ])
    dashboard_session.flush()

    confirmed = Prescription(patient_id=1, status="confirmed")
    unconfirmed = Prescription(patient_id=1, status="needs_review")
    other = Prescription(patient_id=2, status="confirmed")
    dashboard_session.add_all([confirmed, unconfirmed, other])
    dashboard_session.flush()
    item = PrescriptionItem(
        prescription_id=confirmed.id,
        medicine_name="Demo Morning Medicine",
    )
    unconfirmed_item = PrescriptionItem(
        prescription_id=unconfirmed.id,
        medicine_name="Demo Unconfirmed Medicine",
    )
    other_item = PrescriptionItem(
        prescription_id=other.id,
        medicine_name="Demo Other Medicine",
    )
    dashboard_session.add_all([item, unconfirmed_item, other_item])
    dashboard_session.flush()

    dashboard_session.add_all([
        # 09:00, 11:00, and 12:00 on October 10 in Asia/Karachi.
        ScheduleDose(
            prescription_item_id=item.id,
            scheduled_at=datetime(2026, 10, 10, 4, 0, tzinfo=timezone.utc),
            status="taken",
            taken_at=datetime(2026, 10, 10, 4, 5, tzinfo=timezone.utc),
        ),
        ScheduleDose(
            prescription_item_id=item.id,
            scheduled_at=datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc),
            status="pending",
        ),
        ScheduleDose(
            prescription_item_id=item.id,
            scheduled_at=datetime(2026, 10, 10, 7, 0, tzinfo=timezone.utc),
            status="missed",
        ),
        # Immediately outside the local-day boundaries.
        ScheduleDose(
            prescription_item_id=item.id,
            scheduled_at=datetime(2026, 10, 9, 18, 59, tzinfo=timezone.utc),
            status="pending",
        ),
        ScheduleDose(
            prescription_item_id=item.id,
            scheduled_at=datetime(2026, 10, 10, 19, 0, tzinfo=timezone.utc),
            status="pending",
        ),
        # Records for other patients or unconfirmed prescriptions are excluded.
        ScheduleDose(
            prescription_item_id=unconfirmed_item.id,
            scheduled_at=datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc),
            status="pending",
        ),
        ScheduleDose(
            prescription_item_id=other_item.id,
            scheduled_at=datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc),
            status="pending",
        ),
    ])
    add_verification(dashboard_session, 1)
    add_verification(dashboard_session, 1)
    add_verification(dashboard_session, 2)
    dashboard_session.commit()

    snapshot = get_dashboard_snapshot(dashboard_session, now_utc=NOW)

    assert snapshot.patient.demo_name == "Demo Patient"
    assert snapshot.active_prescriptions == 1
    assert snapshot.today.total == 3
    assert snapshot.today.taken == 1
    assert snapshot.today.missed == 1
    assert snapshot.today.remaining == 1
    assert snapshot.next_dose.medicine == "Demo Morning Medicine"
    assert snapshot.next_dose.local_time == "11:00"
    assert snapshot.recent_verifications == 2


def test_dashboard_returns_empty_aggregates_when_patient_has_no_records(dashboard_session):
    dashboard_session.add(Patient(id=1, demo_name="Demo Patient"))
    dashboard_session.commit()

    snapshot = get_dashboard_snapshot(dashboard_session, now_utc=NOW)

    assert snapshot.active_prescriptions == 0
    assert snapshot.today.total == 0
    assert snapshot.today.taken == 0
    assert snapshot.today.missed == 0
    assert snapshot.today.remaining == 0
    assert snapshot.next_dose is None
    assert snapshot.recent_verifications == 0


def test_dashboard_requires_the_demo_patient(dashboard_session):
    with pytest.raises(DashboardPatientNotFoundError):
        get_dashboard_snapshot(dashboard_session, now_utc=NOW)
