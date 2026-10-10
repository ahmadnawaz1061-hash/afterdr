from sqlalchemy import func
from sqlmodel import Session, col, or_, select

from app.models import Medicine


class MedicineRepository:
    def __init__(self, session: Session):
        self.session = session

    def search_by_name(self, q: str, *, limit: int | None = None) -> list[Medicine]:
        query = q.strip()
        statement = select(Medicine)
        if query:
            statement = statement.where(
                or_(
                    col(Medicine.brand_name).icontains(query, autoescape=True),
                    col(Medicine.active_ingredient).icontains(query, autoescape=True),
                )
            )
        statement = statement.order_by(Medicine.brand_name, Medicine.id)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.exec(statement).all())

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
