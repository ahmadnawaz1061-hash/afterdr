import pytest
from sqlalchemy import func
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.models import Medicine, Patient, Prescription, PrescriptionItem
from app.schemas import PrescriptionCreateRequest, PrescriptionMedicine
from app.services.prescription_service import (
    PrescriptionSaveError,
    get_prescription_with_items,
    save_confirmed_prescription,
)


@pytest.fixture
def prescription_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Patient(id=1, demo_name="Demo Patient"))
        session.add(Medicine(
            brand_name="Demo Relief One",
            active_ingredient="Examplemol",
            strength="500 mg",
            dosage_form="tablet",
            route="oral",
        ))
        session.commit()
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def reviewed_payload() -> PrescriptionCreateRequest:
    return PrescriptionCreateRequest(
        patient_id=1,
        status="confirmed",
        medicines=[
            PrescriptionMedicine(
                name="demo relief one",
                strength="500 mg",
                dose="1 tablet",
                frequency="Once daily",
                duration_days=3,
                instructions="After food",
                needs_review=False,
            ),
            PrescriptionMedicine(
                name="Unlisted Visible Medicine",
                strength="25 mg",
                needs_review=False,
            ),
        ],
    )


def test_confirmation_saves_parent_and_items_and_matches_catalog(prescription_engine):
    with Session(prescription_engine) as session:
        prescription = save_confirmed_prescription(session, reviewed_payload())
        prescription_id = prescription.id

    with Session(prescription_engine) as session:
        stored, items = get_prescription_with_items(session, prescription_id)

        assert stored.status == "confirmed"
        assert [item.medicine_name for item in items] == [
            "demo relief one",
            "Unlisted Visible Medicine",
        ]
        assert items[0].medicine_id is not None
        assert items[1].medicine_id is None
        assert all(item.prescription_id == prescription_id for item in items)


def test_confirmation_rolls_back_parent_and_items_when_commit_fails(
    prescription_engine,
    monkeypatch,
):
    with Session(prescription_engine) as session:
        def failing_commit():
            session.flush()
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(session, "commit", failing_commit)
        with pytest.raises(PrescriptionSaveError):
            save_confirmed_prescription(session, reviewed_payload())

    with Session(prescription_engine) as session:
        prescription_count = session.exec(
            select(func.count()).select_from(Prescription)
        ).one()
        item_count = session.exec(
            select(func.count()).select_from(PrescriptionItem)
        ).one()

    assert prescription_count == 0
    assert item_count == 0
