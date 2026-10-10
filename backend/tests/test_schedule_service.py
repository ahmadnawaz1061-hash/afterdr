from datetime import date, datetime, time, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.models import Patient, Prescription, PrescriptionItem, ScheduleDose
from app.schemas import ScheduleCreateRequest
from app.services.schedule_service import (
    UnconfirmedPrescriptionError,
    create_schedule,
    get_today_doses,
    update_dose_status,
)


@pytest.fixture
def schedule_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def add_item(session: Session, *, status: str = "confirmed") -> PrescriptionItem:
    patient = session.get(Patient, 1)
    if patient is None:
        session.add(Patient(id=1, demo_name="Demo Patient"))
        session.flush()
    prescription = Prescription(patient_id=1, status=status)
    session.add(prescription)
    session.flush()
    item = PrescriptionItem(
        prescription_id=prescription.id,
        medicine_name="Demo Scheduled Medicine",
        needs_review=False,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def schedule_request(item_id: int) -> ScheduleCreateRequest:
    return ScheduleCreateRequest(
        prescription_item_id=item_id,
        start_date=date(2026, 10, 10),
        duration_days=5,
        reminder_times=[time(9), time(21)],
        timezone="Asia/Karachi",
    )


def test_two_times_for_five_days_and_repeat_creates_no_duplicates(schedule_engine):
    with Session(schedule_engine) as session:
        item = add_item(session)
        item_id = item.id
        payload = schedule_request(item_id)

        first = create_schedule(session, payload)
        repeated = create_schedule(session, payload)
        doses = list(session.exec(
            select(ScheduleDose).order_by(ScheduleDose.scheduled_at)
        ).all())

    assert first.schedule_id == item_id
    assert first.doses_created == 10
    assert repeated.doses_created == 0
    assert len(doses) == 10
    assert doses[0].scheduled_at == datetime(2026, 10, 10, 4, tzinfo=timezone.utc)
    assert all(dose.status == "pending" for dose in doses)


def test_unconfirmed_prescription_is_rejected_without_doses(schedule_engine):
    with Session(schedule_engine) as session:
        item = add_item(session, status="needs_review")

        with pytest.raises(UnconfirmedPrescriptionError):
            create_schedule(session, schedule_request(item.id))

        assert list(session.exec(select(ScheduleDose)).all()) == []


def test_today_query_respects_local_midnight_across_timezones(schedule_engine):
    with Session(schedule_engine) as session:
        item = add_item(session)
        create_schedule(session, ScheduleCreateRequest(
            prescription_item_id=item.id,
            start_date=date(2026, 1, 2),
            duration_days=1,
            reminder_times=[time(0, 30), time(23, 30)],
            timezone="Asia/Karachi",
        ))
        now = datetime(2026, 1, 1, 20, tzinfo=timezone.utc)

        karachi_today = get_today_doses(
            session,
            "Asia/Karachi",
            now_utc=now,
        )
        utc_today = get_today_doses(session, "UTC", now_utc=now)

    assert [dose.local_time for dose in karachi_today] == ["00:30", "23:30"]
    assert [dose.local_time for dose in utc_today] == ["19:30"]


def test_taken_timestamp_is_utc_and_other_statuses_clear_it(schedule_engine):
    with Session(schedule_engine) as session:
        item = add_item(session)
        create_schedule(session, ScheduleCreateRequest(
            prescription_item_id=item.id,
            start_date=date(2026, 1, 2),
            duration_days=1,
            reminder_times=[time(9)],
            timezone="Asia/Karachi",
        ))
        dose = session.exec(select(ScheduleDose)).one()
        taken_at = datetime(2026, 1, 2, 5, 15, tzinfo=timezone.utc)

        taken = update_dose_status(session, dose.id, "taken", now_utc=taken_at)
        assert taken.taken_at == taken_at
        assert taken.taken_at.tzinfo is timezone.utc

        missed = update_dose_status(session, dose.id, "missed", now_utc=taken_at)
        assert missed.taken_at is None

        pending = update_dose_status(session, dose.id, "pending", now_utc=taken_at)
        assert pending.taken_at is None
