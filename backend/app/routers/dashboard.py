from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.database import get_session
from app.schemas import (
    DashboardNextDose,
    DashboardPatient,
    DashboardResponse,
    DashboardToday,
)
from app.services.dashboard_service import (
    DashboardPatientNotFoundError,
    get_dashboard_snapshot,
)
from app.services.auth_service import AuthenticatedUser, get_current_user


router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> DashboardResponse:
    try:
        snapshot = get_dashboard_snapshot(session, patient_id=user.patient.id)
    except DashboardPatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return DashboardResponse(
        patient=DashboardPatient(
            id=snapshot.patient.id,
            name=snapshot.patient.demo_name,
        ),
        active_prescriptions=snapshot.active_prescriptions,
        today=DashboardToday(
            total_doses=snapshot.today.total,
            taken=snapshot.today.taken,
            remaining=snapshot.today.remaining,
        ),
        next_dose=(
            DashboardNextDose(
                medicine=snapshot.next_dose.medicine,
                time=snapshot.next_dose.local_time,
            )
            if snapshot.next_dose is not None
            else None
        ),
        recent_verifications=snapshot.recent_verifications,
    )
