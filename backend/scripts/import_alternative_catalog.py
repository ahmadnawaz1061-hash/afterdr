"""Run from backend/: python -m scripts.import_alternative_catalog"""

from sqlmodel import Session

from app.database import create_db, engine
from app.services.alternative_catalog import import_catalog


def main():
    create_db()
    with Session(engine) as session:
        inserted, skipped = import_catalog(session)
    print(f"DRAP catalog: {inserted} medicines inserted; {skipped} existing records unchanged.")


if __name__ == "__main__":
    main()
