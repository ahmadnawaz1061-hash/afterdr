from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlmodel import Session, select
from zoneinfo import ZoneInfo

from app.database import get_session
from app.schemas import (
    ScheduleCreateRequest,
    ScheduleCreateResponse,
    ScheduleDoseResponse,
    ScheduleDayResponse,
    ScheduleItemResponse,
    ScheduleRegenerateRequest,
    PrescriptionScheduleResponse,
    ConfirmedPrescriptionOption,
    ScheduleUpdateRequest,
)
from app.services.schedule_service import (
    InvalidTimezoneError,
    NoFutureDosesError,
    ScheduleDoseNotFoundError,
    ScheduleItemNotFoundError,
    ScheduleSaveError,
    UnconfirmedPrescriptionError,
    create_schedule as create_schedule_records,
    get_prescription_schedule,
    get_today_doses,
    regenerate_item_schedule,
    suggest_times,
    update_dose_status,
)
from app.models import Prescription, PrescriptionItem, ScheduleDose
from app.services.auth_service import AuthenticatedUser, get_current_user


router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _owned_item(session: Session, item_id: int, patient_id: int) -> PrescriptionItem:
    item = session.get(PrescriptionItem, item_id)
    prescription = session.get(Prescription, item.prescription_id) if item else None
    if item is None or prescription is None or prescription.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Prescription item not found")
    return item


def _dose_response(
    dose,
    *,
    medicine_name: str,
    local_time: str,
    dose_text: str | None = None,
) -> ScheduleDoseResponse:
    return ScheduleDoseResponse(
        id=dose.id,
        prescription_item_id=dose.prescription_item_id,
        medicine_name=medicine_name,
        dose=dose_text,
        scheduled_at=dose.scheduled_at,
        local_time=local_time,
        status=dose.status,
        taken_at=dose.taken_at,
        is_demo=False,
    )


@router.post("", response_model=ScheduleCreateResponse, status_code=201)
def create_schedule(
    payload: ScheduleCreateRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ScheduleCreateResponse:
    _owned_item(session, payload.prescription_item_id, user.patient.id)
    try:
        result = create_schedule_records(session, payload)
    except ScheduleItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnconfirmedPrescriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ScheduleSaveError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ScheduleCreateResponse(
        schedule_id=result.schedule_id,
        doses_created=result.doses_created,
        status="scheduled",
    )


@router.get("", response_model=PrescriptionScheduleResponse, include_in_schema=False)
def get_schedule(
    prescription_id: int | None = Query(default=None, ge=1),
    timezone: str = Query(default="Asia/Karachi"),
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> PrescriptionScheduleResponse:
    prescriptions = list(session.exec(
        select(Prescription)
        .where(
            Prescription.patient_id == user.patient.id,
            Prescription.status == "confirmed",
        )
        .order_by(Prescription.created_at.desc(), Prescription.id.desc())
    ).all())
    options = [ConfirmedPrescriptionOption(
        prescription_id=record.id,
        created_at=record.created_at,
    ) for record in prescriptions]
    if prescription_id is None:
        if not prescriptions:
            return PrescriptionScheduleResponse(
                prescription_id=None, timezone=timezone, prescriptions=[], items=[]
            )
        prescription_id = prescriptions[0].id
    if prescription_id not in {record.id for record in prescriptions}:
        raise HTTPException(status_code=404, detail="Prescription not found")

    try:
        prescription, views = get_prescription_schedule(session, prescription_id, timezone)
        zone = ZoneInfo(timezone)
    except InvalidTimezoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ScheduleItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnconfirmedPrescriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    items = []
    for view in views:
        grouped = defaultdict(list)
        for dose in view.doses:
            local_date = dose.scheduled_at.astimezone(zone).date()
            grouped[local_date].append(_dose_response(
                dose,
                medicine_name=view.item.medicine_name,
                local_time=dose.scheduled_at.astimezone(zone).strftime("%H:%M"),
                dose_text=view.item.dose,
            ))
        course_start = view.course_start
        course_end = view.course_end
        if course_start is None and view.item.duration_days:
            course_start = prescription.created_at.astimezone(zone).date()
            course_end = course_start + timedelta(days=view.item.duration_days - 1)
        items.append(ScheduleItemResponse(
            prescription_item_id=view.item.id,
            medicine_name=view.item.medicine_name,
            dose=view.item.dose,
            frequency=view.item.frequency,
            duration_days=view.item.duration_days,
            status=view.status,
            reason=view.reason,
            times=list(view.times),
            suggested_times=suggest_times(view.item.frequency) or [],
            course_start=course_start,
            course_end=course_end,
            days=[ScheduleDayResponse(date=day, doses=doses) for day, doses in grouped.items()],
        ))
    return PrescriptionScheduleResponse(
        prescription_id=prescription.id,
        timezone=timezone,
        prescriptions=options,
        items=items,
    )


@router.post(
    "/items/{item_id:int}/regenerate",
    response_model=ScheduleCreateResponse,
    include_in_schema=False,
)
def regenerate_schedule(
    payload: ScheduleRegenerateRequest,
    item_id: int = Path(ge=1),
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ScheduleCreateResponse:
    _owned_item(session, item_id, user.patient.id)
    try:
        result = regenerate_item_schedule(
            session, item_id, payload.reminder_times, payload.timezone
        )
    except ScheduleItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnconfirmedPrescriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (NoFutureDosesError, InvalidTimezoneError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ScheduleSaveError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ScheduleCreateResponse(
        schedule_id=result.schedule_id,
        doses_created=result.doses_created,
        status="scheduled",
    )


@router.get("/today", response_model=list[ScheduleDoseResponse])
def get_today_schedule(
    timezone: str = Query(default="Asia/Karachi"),
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[ScheduleDoseResponse]:
    try:
        doses = get_today_doses(session, timezone, patient_id=user.patient.id)
    except InvalidTimezoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return [
        _dose_response(
            result.dose,
            medicine_name=result.medicine_name,
            local_time=result.local_time,
            dose_text=result.dose_text,
        )
        for result in doses
    ]


@router.patch("/{dose_id:int}", response_model=ScheduleDoseResponse)
def update_schedule_dose(
    payload: ScheduleUpdateRequest,
    dose_id: int = Path(ge=1),
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ScheduleDoseResponse:
    existing = session.get(ScheduleDose, dose_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Schedule dose not found")
    _owned_item(session, existing.prescription_item_id, user.patient.id)
    try:
        dose = update_dose_status(session, dose_id, payload.status)
        item = dose.prescription_item
    except ScheduleDoseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScheduleSaveError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _dose_response(
        dose,
        medicine_name=item.medicine_name,
        dose_text=item.dose,
        local_time=dose.scheduled_at.astimezone(
            ZoneInfo("Asia/Karachi")
        ).strftime("%H:%M"),
    )
