from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool

import app.main as main_module
from app.database import configured_database_url, connection_args
from app.main import app, configured_allowed_origins
from app.models import Medicine, Patient, Prescription, PrescriptionItem, ScheduleDose
from app.repositories.medicine_repository import MedicineRepository
from app.seed import seed_database


@pytest.fixture
def test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def test_insert_and_read_medicine(test_engine):
    medicine = Medicine(
        brand_name="Demo Test Medicine",
        active_ingredient="Examplemol",
        strength="500 mg",
        dosage_form="tablet",
        route="oral",
    )
    with Session(test_engine) as session:
        session.add(medicine)
        session.commit()
        session.refresh(medicine)
        medicine_id = medicine.id

    with Session(test_engine) as session:
        stored = session.get(Medicine, medicine_id)
        assert stored is not None
        assert stored.brand_name == "Demo Test Medicine"
        assert stored.release_type == "immediate"
        assert stored.data_source == "demo_dataset"


def test_unique_schedule_dose_constraint(test_engine):
    scheduled_at = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
    with Session(test_engine) as session:
        patient = Patient(demo_name="Demo Constraint Patient")
        session.add(patient)
        session.flush()
        prescription = Prescription(patient_id=patient.id, status="confirmed")
        session.add(prescription)
        session.flush()
        item = PrescriptionItem(
            prescription_id=prescription.id,
            medicine_name="Demo Original Name",
        )
        session.add(item)
        session.flush()
        session.add(ScheduleDose(prescription_item_id=item.id, scheduled_at=scheduled_at))
        session.commit()

        session.add(ScheduleDose(prescription_item_id=item.id, scheduled_at=scheduled_at))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with Session(test_engine) as session:
        stored = session.exec(select(ScheduleDose)).one()
        assert stored.status == "pending"
        assert stored.scheduled_at == scheduled_at
        assert stored.scheduled_at.tzinfo is timezone.utc


def test_declared_foreign_keys_and_nullable_medicine_match(test_engine):
    schema = inspect(test_engine)
    expected = {
        "prescriptions": {("patient_id", "patients")},
        "prescription_items": {("prescription_id", "prescriptions"), ("medicine_id", "medicines")},
        "schedule_doses": {("prescription_item_id", "prescription_items")},
        "verifications": {("patient_id", "patients"), ("medicine_id", "medicines")},
        "reports": {("verification_id", "verifications")},
    }
    for table, references in expected.items():
        actual = {
            (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
            for foreign_key in schema.get_foreign_keys(table)
        }
        assert actual == references

    columns = {column["name"]: column for column in schema.get_columns("prescription_items")}
    assert columns["medicine_id"]["nullable"] is True
    assert columns["medicine_name"]["nullable"] is False


def test_repository_searches_brand_and_ingredient_case_insensitively(test_engine):
    with Session(test_engine) as session:
        session.add_all([
            Medicine(brand_name="Demo Alpha", active_ingredient="Examplemol", strength="500 mg", dosage_form="tablet", route="oral"),
            Medicine(brand_name="Demo Beta", active_ingredient="Mockadine", strength="10 mg", dosage_form="capsule", route="oral"),
        ])
        session.commit()
        repository = MedicineRepository(session)
        assert [medicine.brand_name for medicine in repository.search_by_name("ALPH")] == ["Demo Alpha"]
        assert [medicine.brand_name for medicine in repository.search_by_name("mockADINE")] == ["Demo Beta"]
        assert repository.get_by_id(repository.search_by_name("Alpha")[0].id).brand_name == "Demo Alpha"
        assert repository.get_by_id(999_999) is None


def test_seed_is_idempotent(test_engine):
    csv_path = Path(__file__).resolve().parent.parent / "data" / "demo_medicines.csv"
    with Session(test_engine) as session:
        assert seed_database(session=session, csv_path=csv_path) == (15, True)
        assert seed_database(session=session, csv_path=csv_path) == (0, False)
        assert len(session.exec(select(Medicine)).all()) == 15
        assert session.get(Patient, 1).demo_name == "Demo Patient"
        medicines = session.exec(select(Medicine)).all()
        assert all(medicine.brand_name.startswith("Demo") for medicine in medicines)
        assert all(medicine.data_source == "demo_dataset" for medicine in medicines)

        groups: dict[tuple[str, str, str, str, str], int] = {}
        for medicine in medicines:
            key = (
                medicine.active_ingredient,
                medicine.strength,
                medicine.dosage_form,
                medicine.route,
                medicine.release_type,
            )
            groups[key] = groups.get(key, 0) + 1
        assert sum(count >= 2 for count in groups.values()) >= 3


def test_database_url_and_driver_options_come_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////var/data/medcare.db")
    assert configured_database_url() == "sqlite:////var/data/medcare.db"
    assert connection_args(configured_database_url()) == {
        "check_same_thread": False,
    }
    assert connection_args("postgresql+psycopg://host/database") == {}

    monkeypatch.setenv("DATABASE_URL", "   ")
    with pytest.raises(RuntimeError, match="must not be empty"):
        configured_database_url()


def test_startup_seeds_an_empty_catalog(monkeypatch, test_engine):
    monkeypatch.setenv("SEED_DEMO_DATA", "true")
    monkeypatch.setattr(main_module, "engine", test_engine)
    monkeypatch.setattr(
        main_module,
        "create_db",
        lambda: SQLModel.metadata.create_all(test_engine),
    )

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    with Session(test_engine) as session:
        assert len(session.exec(select(Medicine)).all()) == 15
        assert session.get(Patient, 1).demo_name == "Demo Patient"


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_the_frontend_origin():
    with TestClient(app) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_an_unconfigured_origin():
    with TestClient(app) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "https://unconfigured.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-origin" not in response.headers


def test_allowed_origins_are_loaded_from_environment(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "https://one.example, https://two.example/ ,https://one.example",
    )
    assert configured_allowed_origins() == [
        "https://one.example",
        "https://two.example",
    ]

    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match=r"HTTP\(S\) origins"):
        configured_allowed_origins()
