import csv
from pathlib import Path

from sqlmodel import Session, func, select

from app.database import create_db, engine
from app.models import Medicine, Patient


DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_medicines.csv"


def _read_medicines(csv_path: Path) -> list[Medicine]:
    with csv_path.open(encoding="utf-8", newline="") as csv_file:
        rows = csv.DictReader(csv_file)
        required = {
            "brand_name", "active_ingredient", "strength", "dosage_form", "route",
            "release_type", "manufacturer", "registration_no", "data_source",
        }
        if rows.fieldnames is None or not required.issubset(rows.fieldnames):
            raise ValueError(f"Medicine CSV is missing required columns: {sorted(required)}")

        medicines = []
        for row in rows:
            if not row["brand_name"].startswith("Demo"):
                raise ValueError("Every seeded medicine brand name must start with 'Demo'")
            if row["data_source"] != "demo_dataset":
                raise ValueError("Every seeded medicine must use data_source='demo_dataset'")
            medicines.append(Medicine(
                brand_name=row["brand_name"],
                active_ingredient=row["active_ingredient"],
                strength=row["strength"],
                dosage_form=row["dosage_form"],
                route=row["route"],
                release_type=row["release_type"] or "immediate",
                manufacturer=row["manufacturer"] or None,
                registration_no=row["registration_no"] or None,
                data_source=row["data_source"],
            ))
    return medicines


def seed_database(*, session: Session, csv_path: Path = DEFAULT_CSV_PATH) -> tuple[int, bool]:
    """Seed an empty catalog and ensure demo Patient 1 exists.

    Returns the number of medicines inserted and whether the patient was created.
    """
    medicine_count = session.exec(select(func.count()).select_from(Medicine)).one()
    inserted = 0
    if medicine_count == 0:
        medicines = _read_medicines(csv_path)
        session.add_all(medicines)
        inserted = len(medicines)

    patient_created = session.get(Patient, 1) is None
    if patient_created:
        session.add(Patient(id=1, demo_name="Demo Patient"))

    session.commit()
    return inserted, patient_created


def main() -> None:
    create_db()
    with Session(engine) as session:
        inserted, patient_created = seed_database(session=session)
    print(f"Seed complete: {inserted} medicines inserted; demo patient created={patient_created}.")


if __name__ == "__main__":
    main()
