"""Database-backed medicine schedule generation and tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session, col, select

from app.models import Prescription, PrescriptionItem, ScheduleDose
from app.schemas import ScheduleCreateRequest


DEMO_PATIENT_ID = 1


class ScheduleServiceError(RuntimeError):
    """Base error for scheduler operations."""


class ScheduleItemNotFoundError(ScheduleServiceError):
    """Raised when a prescription item does not exist."""


class UnconfirmedPrescriptionError(ScheduleServiceError):
    """Raised when schedule creation is attempted before confirmation."""


class ScheduleDoseNotFoundError(ScheduleServiceError):
    """Raised when a dose occurrence does not exist."""


class InvalidTimezoneError(ScheduleServiceError):
    """Raised when an IANA timezone name is unknown."""


class ScheduleSaveError(ScheduleServiceError):
    """Raised after a scheduler transaction has been rolled back."""


@dataclass(frozen=True)
class ScheduleCreationResult:
    schedule_id: int
    doses_created: int


@dataclass(frozen=True)
class TodayDose:
    dose: ScheduleDose
    medicine_name: str
    local_time: str


def timezone_for_name(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidTimezoneError(f"Unknown timezone: {timezone_name}") from exc


def _utc_occurrences(
    start_date: date,
    duration_days: int,
    reminder_times: list[time],
    zone: ZoneInfo,
) -> list[datetime]:
    occurrences = {
        datetime.combine(
            start_date + timedelta(days=day_offset),
            reminder_time,
            tzinfo=zone,
        ).astimezone(timezone.utc)
        for day_offset in range(duration_days)
        for reminder_time in reminder_times
    }
    return sorted(occurrences)


def create_schedule(
    session: Session,
    payload: ScheduleCreateRequest,
) -> ScheduleCreationResult:
    item = session.get(PrescriptionItem, payload.prescription_item_id)
    if item is None:
        raise ScheduleItemNotFoundError(
            f"Prescription item {payload.prescription_item_id} was not found"
        )

    prescription = session.get(Prescription, item.prescription_id)
    if prescription is None:
        raise ScheduleItemNotFoundError(
            f"Prescription item {payload.prescription_item_id} has no prescription"
        )
    if prescription.status != "confirmed":
        raise UnconfirmedPrescriptionError(
            "A schedule can only be created for a confirmed prescription"
        )

    zone = timezone_for_name(payload.timezone)
    occurrences = _utc_occurrences(
        payload.start_date,
        payload.duration_days,
        payload.reminder_times,
        zone,
    )

    try:
        existing = set(session.exec(
            select(ScheduleDose.scheduled_at).where(
                ScheduleDose.prescription_item_id == payload.prescription_item_id,
                col(ScheduleDose.scheduled_at).in_(occurrences),
            )
        ).all())
        new_occurrences = [
            scheduled_at
            for scheduled_at in occurrences
            if scheduled_at not in existing
        ]
        session.add_all([
            ScheduleDose(
                prescription_item_id=payload.prescription_item_id,
                scheduled_at=scheduled_at,
                status="pending",
            )
            for scheduled_at in new_occurrences
        ])
        session.commit()
    except Exception as exc:
        session.rollback()
        raise ScheduleSaveError("The schedule could not be saved") from exc

    return ScheduleCreationResult(
        schedule_id=payload.prescription_item_id,
        doses_created=len(new_occurrences),
    )


def get_today_doses(
    session: Session,
    timezone_name: str,
    *,
    patient_id: int = DEMO_PATIENT_ID,
    now_utc: datetime | None = None,
) -> list[TodayDose]:
    zone = timezone_for_name(timezone_name)
    current_utc = now_utc or datetime.now(timezone.utc)
    if current_utc.tzinfo is None:
        raise ValueError("now_utc must include a timezone")

    local_date = current_utc.astimezone(zone).date()
    utc_start = datetime.combine(local_date, time.min, tzinfo=zone).astimezone(
        timezone.utc
    )
    utc_end = datetime.combine(
        local_date + timedelta(days=1),
        time.min,
        tzinfo=zone,
    ).astimezone(timezone.utc)

    rows = session.exec(
        select(ScheduleDose, PrescriptionItem)
        .join(
            PrescriptionItem,
            ScheduleDose.prescription_item_id == PrescriptionItem.id,
        )
        .join(Prescription, PrescriptionItem.prescription_id == Prescription.id)
        .where(
            Prescription.patient_id == patient_id,
            ScheduleDose.scheduled_at >= utc_start,
            ScheduleDose.scheduled_at < utc_end,
        )
        .order_by(ScheduleDose.scheduled_at, ScheduleDose.id)
    ).all()

    return [
        TodayDose(
            dose=dose,
            medicine_name=item.medicine_name,
            local_time=dose.scheduled_at.astimezone(zone).strftime("%H:%M"),
        )
        for dose, item in rows
    ]


def update_dose_status(
    session: Session,
    dose_id: int,
    status: str,
    *,
    now_utc: datetime | None = None,
) -> ScheduleDose:
    dose = session.get(ScheduleDose, dose_id)
    if dose is None:
        raise ScheduleDoseNotFoundError(f"Schedule dose {dose_id} was not found")

    current_utc = now_utc or datetime.now(timezone.utc)
    if current_utc.tzinfo is None:
        raise ValueError("now_utc must include a timezone")

    try:
        dose.status = status
        dose.taken_at = (
            current_utc.astimezone(timezone.utc) if status == "taken" else None
        )
        session.add(dose)
        session.commit()
        session.refresh(dose)
        return dose
    except Exception as exc:
        session.rollback()
        raise ScheduleSaveError("The dose status could not be updated") from exc
