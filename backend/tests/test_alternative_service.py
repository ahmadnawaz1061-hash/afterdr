import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.models import Medicine
from app.repositories.medicine_repository import MedicineRepository
from app.services.alternative_service import (
    find_alternatives,
    normalize_ingredients,
    normalize_strength,
)


@pytest.fixture
def alternative_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def medicine(brand_name: str, **overrides) -> Medicine:
    attributes = {
        "active_ingredient": "Examplemol",
        "strength": "500 mg",
        "dosage_form": "tablet",
        "route": "oral",
        "release_type": "immediate",
        "data_source": "demo_dataset",
    }
    attributes.update(overrides)
    return Medicine(brand_name=brand_name, **attributes)


def alternative_names(engine, records: list[Medicine]) -> list[str]:
    with Session(engine) as session:
        session.add_all(records)
        session.commit()
        original_id = records[0].id
        matches = find_alternatives(MedicineRepository(session), original_id)
        return [match.medicine.brand_name for match in matches]


def test_strength_units_are_normalized():
    assert normalize_strength("0.5 g") == normalize_strength("500 mg") == "500mg"
    assert normalize_strength("500 mcg") == normalize_strength("0.5 mg") == "0.5mg"


def test_equivalent_strength_units_match(alternative_engine):
    names = alternative_names(alternative_engine, [
        medicine("Demo Original", strength="0.5 g"),
        medicine("Demo Equivalent", strength="500 mg"),
    ])
    assert names == ["Demo Equivalent"]


@pytest.mark.parametrize(
    ("field", "conflicting_value"),
    [
        ("strength", "650 mg"),
        ("route", "topical"),
        ("release_type", "extended"),
    ],
)
def test_conflicting_attributes_are_excluded(
    alternative_engine,
    field,
    conflicting_value,
):
    names = alternative_names(alternative_engine, [
        medicine("Demo Original"),
        medicine("Demo Conflict", **{field: conflicting_value}),
    ])
    assert names == []


def test_combination_ingredients_and_strengths_are_order_independent(alternative_engine):
    assert normalize_ingredients("Examplemol + Samplepril") == normalize_ingredients(
        " samplepril / EXAMPLEMOL "
    )
    names = alternative_names(alternative_engine, [
        medicine(
            "Demo Combination Original",
            active_ingredient="Examplemol + Samplepril",
            strength="500 mg + 5 mg",
        ),
        medicine(
            "Demo Combination Candidate",
            active_ingredient="Samplepril / Examplemol",
            strength="5 mg + 0.5 g",
        ),
    ])
    assert names == ["Demo Combination Candidate"]


@pytest.mark.parametrize(
    "missing_field",
    ["active_ingredient", "strength", "dosage_form", "route", "release_type"],
)
def test_candidates_with_missing_matching_attributes_are_excluded(
    alternative_engine,
    missing_field,
):
    names = alternative_names(alternative_engine, [
        medicine("Demo Original"),
        medicine("Demo Incomplete", **{missing_field: "  "}),
    ])
    assert names == []
