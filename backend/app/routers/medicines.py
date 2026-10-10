from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlmodel import Session

from app.database import get_session
from app.repositories.medicine_repository import MedicineRepository
from app.schemas import AlternativeMedicineResponse, MedicineResponse
from app.services.alternative_service import (
    SUBSTITUTION_NOTICE,
    MedicineNotFoundError,
    find_alternatives,
)
from app.services.auth_service import AuthenticatedUser, get_current_user


router = APIRouter(prefix="/api/medicines", tags=["medicines"])


def _medicine_response(medicine) -> MedicineResponse:
    return MedicineResponse(
        **medicine.model_dump(),
        is_demo=medicine.data_source == "demo_dataset",
    )


@router.get("/search", response_model=list[MedicineResponse])
def search_medicines(
    q: str = Query(default="", max_length=100),
    session: Session = Depends(get_session),
    _user: AuthenticatedUser = Depends(get_current_user),
) -> list[MedicineResponse]:
    medicines = MedicineRepository(session).search_by_name(q, limit=10)
    return [_medicine_response(medicine) for medicine in medicines]


@router.get("/{medicine_id:int}/alternatives", response_model=list[AlternativeMedicineResponse])
def get_alternatives(
    medicine_id: int = Path(ge=1),
    session: Session = Depends(get_session),
    _user: AuthenticatedUser = Depends(get_current_user),
) -> list[AlternativeMedicineResponse]:
    try:
        matches = find_alternatives(MedicineRepository(session), medicine_id)
    except MedicineNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [
        AlternativeMedicineResponse(
            **match.medicine.model_dump(),
            is_demo=match.medicine.data_source == "demo_dataset",
            is_alternative=True,
            match_reasons=list(match.match_reasons),
            notice=SUBSTITUTION_NOTICE,
        )
        for match in matches
    ]
