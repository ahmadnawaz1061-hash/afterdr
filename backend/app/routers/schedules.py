from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlmodel import Session
from zoneinfo import ZoneInfo

from app.database import get_session
from app.schemas import (
    ScheduleCreateRequest,
    ScheduleCreateResponse,
    ScheduleDoseResponse,
    ScheduleUpdateRequest,
)
from app.services.schedule_service import (
    InvalidTimezoneError,
    ScheduleDoseNotFoundError,
    ScheduleItemNotFoundError,
    ScheduleSaveError,
    UnconfirmedPrescriptionError,
    create_schedule as create_schedule_records,
    get_today_doses,
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
) -> ScheduleDoseResponse:
    return ScheduleDoseResponse(
        id=dose.id,
        prescription_item_id=dose.prescription_item_id,
        medicine_name=medicine_name,
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
        local_time=dose.scheduled_at.astimezone(
            ZoneInfo("Asia/Karachi")
        ).strftime("%H:%M"),
    )
