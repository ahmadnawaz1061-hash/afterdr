"""Database aggregates for the demo patient's dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import case, func
from sqlmodel import Session, select

from app.models import Patient, Prescription, PrescriptionItem, ScheduleDose, Verification
from app.services.schedule_service import mark_overdue_doses


DEMO_PATIENT_ID = 1
DEMO_TIMEZONE = ZoneInfo("Asia/Karachi")


class DashboardPatientNotFoundError(LookupError):
    """Raised when the configured demo patient does not exist."""


@dataclass(frozen=True)
class DashboardDoseSummary:
    total: int
    taken: int
    remaining: int


@dataclass(frozen=True)
class DashboardNextDoseResult:
    medicine: str
    local_time: str


@dataclass(frozen=True)
class DashboardSnapshot:
    patient: Patient
    active_prescriptions: int
    today: DashboardDoseSummary
    next_dose: DashboardNextDoseResult | None
    recent_verifications: int


def get_dashboard_snapshot(
    session: Session,
    *,
    patient_id: int = DEMO_PATIENT_ID,
    now_utc: datetime | None = None,
    display_timezone: ZoneInfo = DEMO_TIMEZONE,
) -> DashboardSnapshot:
    """Load dashboard counts and the next dose using aggregate queries."""
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise DashboardPatientNotFoundError(f"Patient {patient_id} was not found")

    current_utc = now_utc or datetime.now(timezone.utc)
    if current_utc.tzinfo is None:
        raise ValueError("now_utc must include a timezone")
    current_utc = current_utc.astimezone(timezone.utc)
    mark_overdue_doses(session, patient_id=patient_id, now_utc=current_utc)

    local_date = current_utc.astimezone(display_timezone).date()
    utc_start = datetime.combine(
        local_date,
        time.min,
        tzinfo=display_timezone,
    ).astimezone(timezone.utc)
    utc_end = datetime.combine(
        local_date + timedelta(days=1),
        time.min,
        tzinfo=display_timezone,
    ).astimezone(timezone.utc)

    active_prescriptions = session.exec(
        select(func.count(Prescription.id)).where(
            Prescription.patient_id == patient_id,
            Prescription.status == "confirmed",
        )
    ).one()

    total_doses, taken_doses = session.exec(
        select(
            func.count(ScheduleDose.id),
            func.coalesce(func.sum(case((ScheduleDose.status == "taken", 1), else_=0)), 0),
        )
        .join(
            PrescriptionItem,
            ScheduleDose.prescription_item_id == PrescriptionItem.id,
        )
        .join(Prescription, PrescriptionItem.prescription_id == Prescription.id)
        .where(
            Prescription.patient_id == patient_id,
            Prescription.status == "confirmed",
            ScheduleDose.scheduled_at >= utc_start,
            ScheduleDose.scheduled_at < utc_end,
        )
    ).one()
    total = int(total_doses or 0)
    taken = int(taken_doses or 0)

    next_row = session.exec(
        select(ScheduleDose.scheduled_at, PrescriptionItem.medicine_name)
        .join(
            PrescriptionItem,
            ScheduleDose.prescription_item_id == PrescriptionItem.id,
        )
        .join(Prescription, PrescriptionItem.prescription_id == Prescription.id)
        .where(
            Prescription.patient_id == patient_id,
            Prescription.status == "confirmed",
            ScheduleDose.status == "pending",
            ScheduleDose.scheduled_at >= current_utc,
        )
        .order_by(ScheduleDose.scheduled_at, ScheduleDose.id)
        .limit(1)
    ).first()
    next_dose = None
    if next_row is not None:
        scheduled_at, medicine_name = next_row
        next_dose = DashboardNextDoseResult(
            medicine=medicine_name,
            local_time=scheduled_at.astimezone(display_timezone).strftime("%H:%M"),
        )

    verification_count = session.exec(
        select(func.count(Verification.id)).where(
            Verification.patient_id == patient_id
        )
    ).one()

    return DashboardSnapshot(
        patient=patient,
        active_prescriptions=int(active_prescriptions or 0),
        today=DashboardDoseSummary(
            total=total,
            taken=taken,
            remaining=total - taken,
        ),
        next_dose=next_dose,
        recent_verifications=int(verification_count or 0),
    )
