"""Database-backed medicine schedule generation and tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session, col, select

from app.models import Prescription, PrescriptionItem, ScheduleDose
from app.schemas import ScheduleCreateRequest


DEMO_PATIENT_ID = 1
OVERDUE_GRACE = timedelta(minutes=30)


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


class NoFutureDosesError(ScheduleServiceError):
    """Raised when a replacement schedule has no future occurrences."""


@dataclass(frozen=True)
class ScheduleCreationResult:
    schedule_id: int
    doses_created: int


@dataclass(frozen=True)
class TodayDose:
    dose: ScheduleDose
    medicine_name: str
    dose_text: str | None
    local_time: str


@dataclass(frozen=True)
class ItemSchedulingResult:
    prescription_item_id: int
    medicine_name: str
    status: str
    times: tuple[str, ...]
    doses_created: int
    reason: str | None = None


@dataclass(frozen=True)
class PrescriptionSchedulingResult:
    items: tuple[ItemSchedulingResult, ...]


@dataclass(frozen=True)
class ScheduleItemView:
    item: PrescriptionItem
    status: str
    reason: str | None
    times: tuple[str, ...]
    course_start: date | None
    course_end: date | None
    doses: tuple[ScheduleDose, ...]


def suggest_times(frequency: str | None) -> list[str] | None:
    """Return conservative reminder suggestions for recognized directions."""
    if frequency is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", frequency.casefold()).strip()
    if not normalized:
        return None
    words = set(normalized.split())
    if words & {"prn", "sos"} or "as needed" in normalized:
        return None

    exact_or_phrase = (
        (("every 12 hours",), ["09:00", "21:00"]),
        (("every 8 hours",), ["06:00", "14:00", "22:00"]),
        (("every 6 hours",), ["06:00", "12:00", "18:00", "00:00"]),
        (("four times daily",), ["08:00", "12:00", "16:00", "20:00"]),
        (("three times daily",), ["08:00", "14:00", "21:00"]),
        (("twice daily",), ["09:00", "21:00"]),
        (("once daily",), ["09:00"]),
        (("at bedtime", "at night"), ["22:00"]),
    )
    for phrases, times in exact_or_phrase:
        if any(phrase in normalized for phrase in phrases):
            return times

    abbreviations = {
        "qid": ["08:00", "12:00", "16:00", "20:00"],
        "tds": ["08:00", "14:00", "21:00"],
        "tid": ["08:00", "14:00", "21:00"],
        "bd": ["09:00", "21:00"],
        "bid": ["09:00", "21:00"],
        "od": ["09:00"],
        "hs": ["22:00"],
    }
    for abbreviation, times in abbreviations.items():
        if abbreviation in words:
            return times
    if "daily" in words:
        return ["09:00"]
    if "morning" in words:
        return ["09:00"]
    if "evening" in words:
        return ["19:00"]
    return None


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
        ).astimezone(datetime_timezone.utc)
        for day_offset in range(duration_days)
        for reminder_time in reminder_times
    }
    return sorted(occurrences)


def _parse_suggested_times(values: list[str]) -> list[time]:
    return [time.fromisoformat(value) for value in values]


def _insert_occurrences(
    session: Session,
    item_id: int,
    occurrences: list[datetime],
) -> int:
    if not occurrences:
        return 0
    existing = set(session.exec(
        select(ScheduleDose.scheduled_at).where(
            ScheduleDose.prescription_item_id == item_id,
            col(ScheduleDose.scheduled_at).in_(occurrences),
        )
    ).all())
    new_occurrences = [value for value in occurrences if value not in existing]
    session.add_all([
        ScheduleDose(
            prescription_item_id=item_id,
            scheduled_at=scheduled_at,
            status="pending",
        )
        for scheduled_at in new_occurrences
    ])
    return len(new_occurrences)


def mark_overdue_doses(
    session: Session,
    *,
    patient_id: int | None = None,
    prescription_id: int | None = None,
    now_utc: datetime | None = None,
) -> int:
    """Persist unanswered doses as missed after the response window."""
    current_utc = now_utc or datetime.now(datetime_timezone.utc)
    if current_utc.tzinfo is None:
        raise ValueError("now_utc must include a timezone")
    cutoff = current_utc.astimezone(datetime_timezone.utc) - OVERDUE_GRACE
    statement = (
        select(ScheduleDose)
        .join(PrescriptionItem, ScheduleDose.prescription_item_id == PrescriptionItem.id)
        .join(Prescription, PrescriptionItem.prescription_id == Prescription.id)
        .where(
            ScheduleDose.status == "pending",
            ScheduleDose.scheduled_at < cutoff,
        )
    )
    if patient_id is not None:
        statement = statement.where(Prescription.patient_id == patient_id)
    if prescription_id is not None:
        statement = statement.where(Prescription.id == prescription_id)
    overdue = list(session.exec(statement).all())
    if not overdue:
        return 0
    try:
        for dose in overdue:
            dose.status = "missed"
            dose.taken_at = None
            session.add(dose)
        session.commit()
    except Exception as exc:
        session.rollback()
        raise ScheduleSaveError("Overdue doses could not be updated") from exc
    return len(overdue)


def auto_schedule_prescription(
    session: Session,
    prescription_id: int,
    start_date: date | None = None,
    timezone: str = "Asia/Karachi",
    *,
    now_utc: datetime | None = None,
) -> PrescriptionSchedulingResult:
    prescription = session.get(Prescription, prescription_id)
    if prescription is None:
        raise ScheduleItemNotFoundError(f"Prescription {prescription_id} was not found")
    if prescription.status != "confirmed":
        raise UnconfirmedPrescriptionError(
            "A schedule can only be created for a confirmed prescription"
        )

    zone = timezone_for_name(timezone)
    current_utc = now_utc or datetime.now(datetime_timezone.utc)
    if current_utc.tzinfo is None:
        raise ValueError("now_utc must include a timezone")
    current_utc = current_utc.astimezone(datetime_timezone.utc)
    local_today = current_utc.astimezone(zone).date()
    course_start = start_date or local_today
    items = list(session.exec(
        select(PrescriptionItem)
        .where(PrescriptionItem.prescription_id == prescription_id)
        .order_by(PrescriptionItem.id)
    ).all())
    results: list[ItemSchedulingResult] = []

    try:
        for item in items:
            reason = None
            suggested = suggest_times(item.frequency)
            if item.needs_review:
                reason = "Review ambiguous instructions before setting times."
            elif not item.duration_days or item.duration_days < 1:
                reason = "Add a valid course duration before setting times."
            elif suggested is None:
                reason = "Set reminder times for this frequency."

            if reason:
                results.append(ItemSchedulingResult(
                    prescription_item_id=item.id,
                    medicine_name=item.medicine_name,
                    status="needs_times",
                    times=(),
                    doses_created=0,
                    reason=reason,
                ))
                continue

            occurrences = _utc_occurrences(
                course_start,
                item.duration_days,
                _parse_suggested_times(suggested),
                zone,
            )
            if course_start == local_today:
                occurrences = [value for value in occurrences if value > current_utc]
            created = _insert_occurrences(session, item.id, occurrences)
            results.append(ItemSchedulingResult(
                prescription_item_id=item.id,
                medicine_name=item.medicine_name,
                status="scheduled",
                times=tuple(suggested),
                doses_created=created,
            ))
        session.commit()
    except Exception as exc:
        session.rollback()
        raise ScheduleSaveError("The automatic schedule could not be saved") from exc
    return PrescriptionSchedulingResult(items=tuple(results))


def regenerate_item_schedule(
    session: Session,
    item_id: int,
    reminder_times: list[time],
    timezone: str,
    *,
    now_utc: datetime | None = None,
) -> ScheduleCreationResult:
    item = session.get(PrescriptionItem, item_id)
    if item is None:
        raise ScheduleItemNotFoundError(f"Prescription item {item_id} was not found")
    prescription = session.get(Prescription, item.prescription_id)
    if prescription is None or prescription.status != "confirmed":
        raise UnconfirmedPrescriptionError(
            "A schedule can only be created for a confirmed prescription"
        )
    if not reminder_times:
        raise NoFutureDosesError("Choose at least one reminder time")
    if not item.duration_days or item.duration_days < 1:
        raise NoFutureDosesError("Add a valid course duration before setting times")

    zone = timezone_for_name(timezone)
    current_utc = now_utc or datetime.now(datetime_timezone.utc)
    if current_utc.tzinfo is None:
        raise ValueError("now_utc must include a timezone")
    current_utc = current_utc.astimezone(datetime_timezone.utc)
    all_doses = list(session.exec(
        select(ScheduleDose)
        .where(ScheduleDose.prescription_item_id == item_id)
        .order_by(ScheduleDose.scheduled_at)
    ).all())
    if all_doses:
        earliest_scheduled_day = min(
            dose.scheduled_at.astimezone(zone).date() for dose in all_doses
        )
        course_start = min(earliest_scheduled_day, current_utc.astimezone(zone).date())
    else:
        course_start = current_utc.astimezone(zone).date()
    occurrences = [value for value in _utc_occurrences(
        course_start, item.duration_days, reminder_times, zone
    ) if value > current_utc]
    if not occurrences:
        raise NoFutureDosesError("The selected times do not create any future doses")

    try:
        for dose in all_doses:
            if dose.status == "pending" and dose.scheduled_at > current_utc:
                session.delete(dose)
        session.flush()
        created = _insert_occurrences(session, item_id, occurrences)
        session.commit()
    except Exception as exc:
        session.rollback()
        raise ScheduleSaveError("The schedule could not be regenerated") from exc
    return ScheduleCreationResult(schedule_id=item_id, doses_created=created)


def get_prescription_schedule(
    session: Session,
    prescription_id: int,
    timezone: str,
) -> tuple[Prescription, tuple[ScheduleItemView, ...]]:
    prescription = session.get(Prescription, prescription_id)
    if prescription is None:
        raise ScheduleItemNotFoundError(f"Prescription {prescription_id} was not found")
    if prescription.status != "confirmed":
        raise UnconfirmedPrescriptionError(
            "A schedule can only be viewed for a confirmed prescription"
        )
    mark_overdue_doses(session, prescription_id=prescription_id)
    zone = timezone_for_name(timezone)
    items = list(session.exec(
        select(PrescriptionItem)
        .where(PrescriptionItem.prescription_id == prescription_id)
        .order_by(PrescriptionItem.id)
    ).all())
    item_ids = [item.id for item in items]
    doses = list(session.exec(
        select(ScheduleDose)
        .where(col(ScheduleDose.prescription_item_id).in_(item_ids))
        .order_by(ScheduleDose.scheduled_at, ScheduleDose.id)
    ).all()) if item_ids else []
    by_item: dict[int, list[ScheduleDose]] = {item_id: [] for item_id in item_ids}
    for dose in doses:
        by_item[dose.prescription_item_id].append(dose)

    views = []
    for item in items:
        item_doses = by_item[item.id]
        local_dates = [dose.scheduled_at.astimezone(zone).date() for dose in item_doses]
        times = tuple(sorted({
            dose.scheduled_at.astimezone(zone).strftime("%H:%M")
            for dose in item_doses
        }))
        reason = None
        if item.needs_review:
            reason = "Review ambiguous instructions before setting times."
        elif not item.duration_days:
            reason = "Add a valid course duration before setting times."
        elif not item_doses:
            reason = "Set reminder times for this frequency."
        views.append(ScheduleItemView(
            item=item,
            status="scheduled" if item_doses else "needs_times",
            reason=reason,
            times=times,
            course_start=min(local_dates) if local_dates else None,
            course_end=max(local_dates) if local_dates else None,
            doses=tuple(item_doses),
        ))
    return prescription, tuple(views)


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
        created = _insert_occurrences(
            session, payload.prescription_item_id, occurrences
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        raise ScheduleSaveError("The schedule could not be saved") from exc

    return ScheduleCreationResult(
        schedule_id=payload.prescription_item_id,
        doses_created=created,
    )


def get_today_doses(
    session: Session,
    timezone_name: str,
    *,
    patient_id: int = DEMO_PATIENT_ID,
    now_utc: datetime | None = None,
) -> list[TodayDose]:
    zone = timezone_for_name(timezone_name)
    current_utc = now_utc or datetime.now(datetime_timezone.utc)
    if current_utc.tzinfo is None:
        raise ValueError("now_utc must include a timezone")
    mark_overdue_doses(session, patient_id=patient_id, now_utc=current_utc)

    local_date = current_utc.astimezone(zone).date()
    utc_start = datetime.combine(local_date, time.min, tzinfo=zone).astimezone(
        datetime_timezone.utc
    )
    utc_end = datetime.combine(
        local_date + timedelta(days=1),
        time.min,
        tzinfo=zone,
    ).astimezone(datetime_timezone.utc)

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
            dose_text=item.dose,
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

    current_utc = now_utc or datetime.now(datetime_timezone.utc)
    if current_utc.tzinfo is None:
        raise ValueError("now_utc must include a timezone")

    try:
        dose.status = status
        dose.taken_at = (
            current_utc.astimezone(datetime_timezone.utc) if status == "taken" else None
        )
        session.add(dose)
        session.commit()
        session.refresh(dose)
        return dose
    except Exception as exc:
        session.rollback()
        raise ScheduleSaveError("The dose status could not be updated") from exc
