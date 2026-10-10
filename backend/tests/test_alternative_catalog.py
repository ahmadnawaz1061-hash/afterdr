import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.database import get_session
from app.main import app
from app.models import Medicine, Patient
from app.services.alternative_catalog import import_catalog, load_catalog, provenance
from app.services.auth_service import get_current_user


@pytest.fixture
def catalog_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def catalog_client(catalog_engine):
    with Session(catalog_engine) as session:
        import_catalog(session)
        session.add(Medicine(brand_name="Demo", active_ingredient="Paracetamol", strength="500 mg", dosage_form="tablet", route="oral"))
        session.commit()
    def override_session():
        with Session(catalog_engine) as session:
            yield session
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_session, None)


def test_import_is_idempotent_and_does_not_create_patient_records(catalog_engine):
    count = len(load_catalog()["records"])
    with Session(catalog_engine) as session:
        assert import_catalog(session) == (count, 0)
        assert import_catalog(session) == (0, count)
        assert len(session.exec(select(Medicine)).all()) == count
        assert session.exec(select(Patient)).all() == []


def test_conflict_rolls_back_all_import_additions(catalog_engine):
    with Session(catalog_engine) as session:
        session.add(Medicine(brand_name="Existing", active_ingredient="Different", strength="10 mg", dosage_form="tablet", route="oral", registration_no="003068"))
        session.commit()
        with pytest.raises(ValueError, match="conflicts"):
            import_catalog(session)
        records = session.exec(select(Medicine)).all()
        assert len(records) == 1 and records[0].brand_name == "Existing"


def test_catalog_sources_are_explicit_and_no_fictional_rows_are_present():
    catalog = load_catalog()
    assert catalog["source_checked_at"] == "2026-10-10"
    assert all(row["data_source"] == "drap_pk" for row in catalog["records"])
    assert not any(row["brand_name"].startswith("Demo") for row in catalog["records"])
    assert len(catalog["records"]) >= 150
    assert len({row["registration_no"] for row in catalog["records"]}) == len(catalog["records"])
    assert len({row["source_url"] for row in catalog["records"]}) >= 30
    assert all(row.get("source_composition") for row in catalog["records"][8:])
    assert not any(row["registration_no"] == "019652" for row in catalog["records"])


def test_search_uses_only_documented_pakistan_records(catalog_client):
    response = catalog_client.get("/api/medicines/search", params={"q": "  PARA  ", "catalog": "drap_pk"})
    assert response.status_code == 200
    records = response.json()
    assert len(records) == 10
    assert all("para" in row["active_ingredient"].lower() or "para" in row["brand_name"].lower() for row in records)
    assert all(not row["is_demo"] and row["source_url"].startswith("https://e.dra.gov.pk/") for row in records)
    assert catalog_client.get("/api/medicines/search", params={"q": "%", "catalog": "drap_pk"}).json() == []


def test_every_catalog_record_is_reachable_without_page_overlap(catalog_client):
    rows = []
    count = len(load_catalog()["records"])
    for offset in range(0, count + 10, 10):
        response = catalog_client.get("/api/medicines/search", params={"catalog": "drap_pk", "offset": offset})
        assert response.status_code == 200
        page = response.json()
        assert len(page) <= 10
        rows.extend(page)
    assert len(rows) == count
    assert len({row["registration_no"] for row in rows}) == count
    assert not any(row["is_demo"] for row in rows)
    assert catalog_client.get("/api/medicines/search", params={"catalog": "drap_pk", "offset": -1}).status_code == 422
    assert catalog_client.get("/api/medicines/search", params={"catalog": "drap_pk", "limit": 51}).status_code == 422


def test_manufacturer_leaflet_enriches_only_the_specific_pakistan_registration(catalog_client):
    rows = catalog_client.get("/api/medicines/search", params={"q": "Getzid", "catalog": "drap_pk"}).json()
    assert len(rows) == 1
    assert rows[0]["registration_no"] == "102855"
    assert (rows[0]["route"], rows[0]["release_type"]) == ("oral", "modified")
    assert rows[0]["formulation_source_url"].startswith("https://getzpharma.com/")
    assert catalog_client.get(f"/api/medicines/{rows[0]['id']}/alternatives", params={"catalog": "drap_pk"}).json() == []


def test_sourced_candidates_have_explanations_and_notice(catalog_client):
    records = catalog_client.get("/api/medicines/search", params={"q": "Panadol", "catalog": "drap_pk"}).json()
    response = catalog_client.get(f"/api/medicines/{records[0]['id']}/alternatives", params={"catalog": "drap_pk"})
    assert response.status_code == 200
    candidates = response.json()
    assert [row["brand_name"] for row in candidates] == ["Provas"]
    assert candidates[0]["is_alternative"] is True
    assert len(candidates[0]["match_reasons"]) == 5
    assert candidates[0]["notice"] == "Confirm with your pharmacist or prescriber before substituting."
    assert candidates[0]["formulation_source_url"].startswith("https://www.dra.gov.pk/")


def test_incomplete_records_do_not_return_alternatives(catalog_client):
    records = catalog_client.get("/api/medicines/search", params={"q": "Bactrim", "catalog": "drap_pk"}).json()
    assert catalog_client.get(f"/api/medicines/{records[0]['id']}/alternatives", params={"catalog": "drap_pk"}).json() == []


def test_unknown_ids_and_other_catalogs_are_rejected(catalog_client, catalog_engine):
    assert catalog_client.get("/api/medicines/999/alternatives", params={"catalog": "drap_pk"}).status_code == 404
    with Session(catalog_engine) as session:
        demo = session.exec(select(Medicine).where(Medicine.brand_name == "Demo")).one()
        assert catalog_client.get(f"/api/medicines/{demo.id}/alternatives", params={"catalog": "drap_pk"}).status_code == 404
    assert catalog_client.get("/api/medicines/search", params={"catalog": "other"}).status_code == 422


def test_source_markers_do_not_validate_tampered_catalog_records(catalog_engine):
    with Session(catalog_engine) as session:
        import_catalog(session)
        medicine = session.exec(select(Medicine).where(Medicine.brand_name == "Panadol")).one()
        assert provenance(medicine)
        medicine.strength = "650 mg"
        assert provenance(medicine) == {}


def test_pakistan_search_requires_authentication(catalog_client):
    user_override = app.dependency_overrides.pop(get_current_user)
    try:
        assert catalog_client.get("/api/medicines/search", params={"catalog": "drap_pk"}).status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = user_override
