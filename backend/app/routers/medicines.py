from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlmodel import Session, col, select
from typing import Literal

from app.database import get_session
from app.repositories.medicine_repository import MedicineRepository
from app.schemas import AlternativeMedicineResponse, MedicineResponse
from app.models import Medicine
from app.services.alternative_catalog import load_catalog, provenance
from app.services.medicine_search import rank_medicines
from app.services.alternative_service import (
    SUBSTITUTION_NOTICE,
    MedicineNotFoundError,
    find_alternatives,
)
from app.services.auth_service import AuthenticatedUser, get_current_user


router = APIRouter(prefix="/api/medicines", tags=["medicines"])


class CatalogMedicineResponse(MedicineResponse):
    similar_spelling: bool = False
    source_url: str | None = None
    source_checked_at: str | None = None
    formulation_source_url: str | None = None
    source_search_query: str | None = None


class CatalogAlternativeResponse(AlternativeMedicineResponse):
    source_url: str | None = None
    source_checked_at: str | None = None
    formulation_source_url: str | None = None
    source_search_query: str | None = None


def _medicine_response(medicine) -> CatalogMedicineResponse:
    return CatalogMedicineResponse(
        **medicine.model_dump(),
        is_demo=medicine.data_source == "demo_dataset",
        **provenance(medicine),
    )


@router.get("/search", response_model=list[CatalogMedicineResponse], response_model_exclude_unset=True)
def search_medicines(
    q: str = Query(default="", max_length=100),
    catalog: Literal["all", "drap_pk"] = Query(default="all"),
    offset: int = Query(default=0, ge=0, le=10000),
    limit: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
    _user: AuthenticatedUser = Depends(get_current_user),
) -> list[CatalogMedicineResponse]:
    if catalog == "drap_pk":
        registrations = [record["registration_no"] for record in load_catalog()["records"]]
        statement = select(Medicine).where(Medicine.data_source == "drap_pk", col(Medicine.registration_no).in_(registrations))
        medicines = session.exec(statement.order_by(Medicine.brand_name, Medicine.id)).all()
        # A source marker alone is insufficient: require an exact sourced record.
        medicines = [medicine for medicine in medicines if provenance(medicine)]
    else:
        medicines = session.exec(select(Medicine)).all()
    matches = rank_medicines(medicines, q)
    return [
        _medicine_response(match.medicine).model_copy(update={"similar_spelling": match.similar_spelling})
        for match in matches[offset:offset + limit]
    ]


@router.get("/{medicine_id:int}/alternatives", response_model=list[CatalogAlternativeResponse], response_model_exclude_unset=True)
def get_alternatives(
    medicine_id: int = Path(ge=1),
    catalog: Literal["all", "drap_pk"] = Query(default="all"),
    session: Session = Depends(get_session),
    _user: AuthenticatedUser = Depends(get_current_user),
) -> list[CatalogAlternativeResponse]:
    repository = MedicineRepository(session)
    if catalog == "drap_pk":
        original = repository.get_by_id(medicine_id)
        if original is None or not provenance(original):
            raise HTTPException(status_code=404, detail="Medicine was not found in the documented Pakistan catalog")
    try:
        matches = find_alternatives(repository, medicine_id)
    except MedicineNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [
        CatalogAlternativeResponse(
            **match.medicine.model_dump(),
            is_demo=match.medicine.data_source == "demo_dataset",
            is_alternative=True,
            match_reasons=list(match.match_reasons),
            notice=SUBSTITUTION_NOTICE,
            **provenance(match.medicine),
        )
        for match in matches
        if catalog == "all" or provenance(match.medicine)
    ]
