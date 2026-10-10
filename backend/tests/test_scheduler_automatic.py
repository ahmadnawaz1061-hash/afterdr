from datetime import date, datetime, time, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.models import Patient, Prescription, PrescriptionItem, ScheduleDose
from app.services.schedule_service import (
    UnconfirmedPrescriptionError,
    auto_schedule_prescription,
    mark_overdue_doses,
    regenerate_item_schedule,
    suggest_times,
)


@pytest.fixture
def engine():
    value = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(value)
    yield value
    SQLModel.metadata.drop_all(value)
    value.dispose()


def add_prescription(session: Session, *, status="confirmed", items=None):
    session.add(Patient(id=1, demo_name="Scheduler Patient"))
    prescription = Prescription(patient_id=1, status=status)
    session.add(prescription)
    session.flush()
    records = []
    for values in items or []:
        item = PrescriptionItem(prescription_id=prescription.id, **values)
        session.add(item)
        records.append(item)
    session.commit()
    for item in records:
        session.refresh(item)
    return prescription, records


@pytest.mark.parametrize(("frequency", "expected"), [
    ("once daily", ["09:00"]), ("OD", ["09:00"]), ("daily", ["09:00"]),
    ("twice daily", ["09:00", "21:00"]), ("BD", ["09:00", "21:00"]),
    ("BID", ["09:00", "21:00"]),
    ("three times daily", ["08:00", "14:00", "21:00"]),
    ("TDS", ["08:00", "14:00", "21:00"]), ("TID", ["08:00", "14:00", "21:00"]),
    ("four times daily", ["08:00", "12:00", "16:00", "20:00"]),
    ("QID", ["08:00", "12:00", "16:00", "20:00"]),
    ("every 12 hours", ["09:00", "21:00"]),
    ("every 8 hours", ["06:00", "14:00", "22:00"]),
    ("every 6 hours", ["06:00", "12:00", "18:00", "00:00"]),
    ("at bedtime", ["22:00"]), ("HS", ["22:00"]), ("at night", ["22:00"]),
    ("morning", ["09:00"]), ("evening", ["19:00"]),
])
def test_suggest_times_recognizes_only_supported_wording(frequency, expected):
    assert suggest_times(frequency) == expected


@pytest.mark.parametrize("frequency", [None, "", "unclear", "as needed", "SOS", "PRN"])
def test_suggest_times_does_not_guess(frequency):
    assert suggest_times(frequency) is None


def test_auto_schedule_twice_daily_for_five_days_and_is_idempotent(engine):
    with Session(engine) as session:
        prescription, items = add_prescription(session, items=[{
            "medicine_name": "Course medicine", "frequency": "twice daily",
            "duration_days": 5, "needs_review": False,
        }])
        now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        first = auto_schedule_prescription(
            session, prescription.id, date(2026, 10, 10), "Asia/Karachi", now_utc=now
        )
        repeated = auto_schedule_prescription(
            session, prescription.id, date(2026, 10, 10), "Asia/Karachi", now_utc=now
        )
        doses = list(session.exec(select(ScheduleDose)).all())

    assert first.items[0].doses_created == 10
    assert first.items[0].times == ("09:00", "21:00")
    assert repeated.items[0].doses_created == 0
    assert len(doses) == 10


def test_auto_schedule_marks_ambiguous_and_missing_duration_as_needs_times(engine):
    with Session(engine) as session:
        prescription, _ = add_prescription(session, items=[
            {"medicine_name": "Ambiguous", "frequency": "daily", "duration_days": 5, "needs_review": True},
            {"medicine_name": "No duration", "frequency": "daily", "duration_days": None, "needs_review": False},
        ])
        result = auto_schedule_prescription(
            session, prescription.id, date(2026, 10, 10), "Asia/Karachi",
            now_utc=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )

    assert [item.status for item in result.items] == ["needs_times", "needs_times"]
    assert all(item.reason for item in result.items)


def test_auto_schedule_skips_times_already_passed_today(engine):
    with Session(engine) as session:
        prescription, _ = add_prescription(session, items=[{
            "medicine_name": "Today medicine", "frequency": "twice daily",
            "duration_days": 5, "needs_review": False,
        }])
        result = auto_schedule_prescription(
            session, prescription.id, None, "Asia/Karachi",
            now_utc=datetime(2026, 10, 10, 10, tzinfo=timezone.utc),
        )
        doses = list(session.exec(select(ScheduleDose).order_by(ScheduleDose.scheduled_at)).all())

    assert result.items[0].doses_created == 9
    assert doses[0].scheduled_at == datetime(2026, 10, 10, 16, tzinfo=timezone.utc)


def test_regenerate_keeps_taken_and_missed_and_replaces_future_pending(engine):
    with Session(engine) as session:
        prescription, items = add_prescription(session, items=[{
            "medicine_name": "History medicine", "frequency": "twice daily",
            "duration_days": 3, "needs_review": False,
        }])
        auto_schedule_prescription(
            session, prescription.id, date(2026, 10, 9), "Asia/Karachi",
            now_utc=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )
        doses = list(session.exec(select(ScheduleDose).order_by(ScheduleDose.scheduled_at)).all())
        doses[0].status = "taken"
        doses[1].status = "missed"
        session.add_all(doses[:2])
        session.commit()
        kept_ids = {doses[0].id, doses[1].id}
        replaced_times = {
            dose.scheduled_at for dose in doses
            if dose.status == "pending"
            and dose.scheduled_at > datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        }

        regenerate_item_schedule(
            session, items[0].id, [time(10)], "Asia/Karachi",
            now_utc=datetime(2026, 10, 10, 12, tzinfo=timezone.utc),
        )
        remaining = list(session.exec(select(ScheduleDose).order_by(ScheduleDose.scheduled_at)).all())

    kept = [dose for dose in remaining if dose.id in kept_ids]
    assert {dose.status for dose in kept} == {"taken", "missed"}
    assert replaced_times.isdisjoint({dose.scheduled_at for dose in remaining})
    assert any(dose.status == "pending" for dose in remaining)


def test_auto_schedule_rejects_unconfirmed_prescription(engine):
    with Session(engine) as session:
        prescription, _ = add_prescription(session, status="needs_review", items=[{
            "medicine_name": "Unconfirmed", "frequency": "daily",
            "duration_days": 5, "needs_review": False,
        }])
        with pytest.raises(UnconfirmedPrescriptionError):
            auto_schedule_prescription(session, prescription.id)
        assert list(session.exec(select(ScheduleDose)).all()) == []


def test_overdue_pending_dose_is_marked_missed_after_response_window(engine):
    with Session(engine) as session:
        _, items = add_prescription(session, items=[{
            "medicine_name": "Reminder medicine", "dose": "1 tablet",
            "frequency": "daily", "duration_days": 1, "needs_review": False,
        }])
        dose = ScheduleDose(
            prescription_item_id=items[0].id,
            scheduled_at=datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc),
            status="pending",
        )
        session.add(dose)
        session.commit()
        session.refresh(dose)

        changed = mark_overdue_doses(
            session,
            patient_id=1,
            now_utc=datetime(2026, 10, 10, 8, 31, tzinfo=timezone.utc),
        )
        session.refresh(dose)

    assert changed == 1
    assert dose.status == "missed"
    assert dose.taken_at is None


def test_response_window_and_completed_doses_are_preserved(engine):
    with Session(engine) as session:
        _, items = add_prescription(session, items=[{
            "medicine_name": "Checklist medicine", "frequency": "twice daily",
            "duration_days": 1, "needs_review": False,
        }])
        recent = ScheduleDose(
            prescription_item_id=items[0].id,
            scheduled_at=datetime(2026, 10, 10, 8, 1, tzinfo=timezone.utc),
            status="pending",
        )
        taken = ScheduleDose(
            prescription_item_id=items[0].id,
            scheduled_at=datetime(2026, 10, 10, 7, 0, tzinfo=timezone.utc),
            status="taken",
            taken_at=datetime(2026, 10, 10, 7, 0, tzinfo=timezone.utc),
        )
        session.add_all([recent, taken])
        session.commit()

        changed = mark_overdue_doses(
            session,
            patient_id=1,
            now_utc=datetime(2026, 10, 10, 8, 30, tzinfo=timezone.utc),
        )
        session.refresh(recent)
        session.refresh(taken)

    assert changed == 0
    assert recent.status == "pending"
    assert taken.status == "taken"
    assert taken.taken_at is not None
