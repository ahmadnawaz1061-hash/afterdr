import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.models import Medicine
from app.repositories.medicine_repository import MedicineRepository
from app.services.alternative_service import (
    MedicineNotFoundError,
    find_alternatives,
    normalize_ingredients,
    normalize_strength,
    normalize_matching_strength,
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


def test_swapped_combination_amounts_do_not_match(alternative_engine):
    names = alternative_names(alternative_engine, [
        medicine("Original", active_ingredient="Examplemol + Samplepril", strength="500 mg + 5 mg"),
        medicine("Wrong amounts", active_ingredient="Samplepril + Examplemol", strength="500 mg + 5 mg"),
    ])
    assert names == []


@pytest.mark.parametrize("strength", [
    "", "unknown", "500", "-500 mg", "0 mg", "about 500 mg", "500 mg extra",
    "10 IU", "5%", "500 mg +", "500 mg/0 mL", "500 mg + 5 mg/5mL",
])
def test_unsupported_or_ambiguous_strength_is_excluded(strength, alternative_engine):
    assert normalize_matching_strength(strength) is None
    assert alternative_names(alternative_engine, [
        medicine("Original", strength=strength), medicine("Candidate", strength=strength),
    ]) == []


@pytest.mark.parametrize(("first", "second"), [
    ("100 mg/mL", "500 mg/5 mL"), ("0.5 g/5 mL", "100 mg/ml"),
    ("1000 mcg", "1 mg"), ("500 µg", "0.5 mg"), ("500 μg", ".5 mg"),
    (".5 milligrams", "500 micrograms"), ("1 mg/3 ml", "2 mg/6 ml"),
])
def test_exact_unit_and_concentration_equivalence(first, second, alternative_engine):
    assert normalize_matching_strength(first) == normalize_matching_strength(second)
    assert alternative_names(alternative_engine, [
        medicine("Original", strength=first), medicine("Candidate", strength=second),
    ]) == ["Candidate"]


def test_different_concentrations_are_not_rounded_into_match(alternative_engine):
    assert alternative_names(alternative_engine, [
        medicine("Original", strength="1 mg/3 ml"),
        medicine("Different", strength="0.3333333333333333333333333333 mg/ml"),
        medicine("Mass only", strength="1 mg"),
    ]) == []


@pytest.mark.parametrize("ingredients", ["Examplemol +", "Examplemol + Examplemol", "unknown"])
def test_ambiguous_ingredients_are_excluded(ingredients, alternative_engine):
    assert alternative_names(alternative_engine, [
        medicine("Original", active_ingredient=ingredients),
        medicine("Candidate", active_ingredient=ingredients),
    ]) == []


def test_component_counts_must_match(alternative_engine):
    assert alternative_names(alternative_engine, [
        medicine("Original", active_ingredient="Examplemol + Samplepril"),
        medicine("Candidate", active_ingredient="Examplemol + Samplepril"),
    ]) == []


@pytest.mark.parametrize("field", ["active_ingredient", "strength", "dosage_form", "route", "release_type", "data_source"])
def test_unknown_attributes_are_not_evidence_of_equivalence(field, alternative_engine):
    assert alternative_names(alternative_engine, [
        medicine("Original", **{field: "unknown"}), medicine("Candidate", **{field: "unknown"}),
    ]) == []


def test_salts_forms_and_extra_ingredients_remain_distinct(alternative_engine):
    assert alternative_names(alternative_engine, [
        medicine("Original"), medicine("Salt", active_ingredient="Examplemol hydrochloride"),
        medicine("Capsule", dosage_form="capsule"),
        medicine("Combination", active_ingredient="Examplemol + Samplepril", strength="500 mg + 5 mg"),
    ]) == []


def test_real_and_demo_sources_do_not_mix(alternative_engine):
    assert alternative_names(alternative_engine, [
        medicine("Original", data_source="drap_pk"), medicine("Demo candidate"),
    ]) == []


def test_missing_original_raises_and_original_is_never_returned(alternative_engine):
    with Session(alternative_engine) as session:
        with pytest.raises(MedicineNotFoundError):
            find_alternatives(MedicineRepository(session), 999)
    assert alternative_names(alternative_engine, [medicine("Only record")]) == []


@pytest.mark.parametrize(("first", "second"), [
    ("5%", "10%"), ("10 IU", "20 IU"), ("unknown", "n/a"),
])
def test_legacy_helper_keeps_unsupported_values_distinct_for_other_modules(first, second):
    assert normalize_strength(first) != normalize_strength(second)
    assert normalize_matching_strength(first) is None
    assert normalize_matching_strength(second) is None


def test_legacy_helper_preserves_unit_volume_and_combination_ordering():
    assert normalize_strength("1 L") == "1000ml"
    assert normalize_strength("5 mg + 0.5 g") == normalize_strength("500 mg + 5 mg") == "500mg+5mg"
    assert normalize_strength("500 mg/5 mL") == "500mg/5ml"
