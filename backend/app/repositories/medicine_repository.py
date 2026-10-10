from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Medicine
from app.services.medicine_search import rank_medicines


class MedicineRepository:
    def __init__(self, session: Session):
        self.session = session

    def search_by_name(self, q: str, *, limit: int | None = None) -> list[Medicine]:
        medicines = list(self.session.exec(select(Medicine)).all())
        matches = rank_medicines(medicines, q)
        return [match.medicine for match in (matches[:limit] if limit is not None else matches)]

    def get_by_id(self, medicine_id: int) -> Medicine | None:
        return self.session.get(Medicine, medicine_id)

    def find_by_registration_no(self, registration_no: str) -> Medicine | None:
        normalized = registration_no.strip().casefold()
        if not normalized:
            return None
        return self.session.exec(
            select(Medicine).where(
                func.lower(func.trim(Medicine.registration_no)) == normalized
            )
        ).first()

    def find_by_brand_name(self, brand_name: str) -> Medicine | None:
        normalized = brand_name.strip().casefold()
        if not normalized:
            return None
        return self.session.exec(
            select(Medicine).where(
                func.lower(func.trim(Medicine.brand_name)) == normalized
            )
        ).first()
