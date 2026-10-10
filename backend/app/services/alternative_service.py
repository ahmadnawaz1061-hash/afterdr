"""Deterministic catalog matching for potential medicine alternatives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.models import Medicine
from app.repositories.medicine_repository import MedicineRepository


SUBSTITUTION_NOTICE = "Confirm with your pharmacist or prescriber before substituting."
MATCH_REASONS = (
    "Same active ingredient(s)",
    "Equivalent normalized strength",
    "Same dosage form",
    "Same route",
    "Same release type",
)

_INGREDIENT_SEPARATOR = re.compile(r"\s*(?:\+|/|,|;|\band\b)\s*", re.IGNORECASE)
_STRENGTH_SEPARATOR = re.compile(r"\s*(?:\+|;)\s*")
_AMOUNT_WITH_UNIT = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>milligrams?|micrograms?|millilit(?:er|re)s?|grams?|lit(?:er|re)s?|mcg|mg|kg|ml|ug|g|l)\b",
    re.IGNORECASE,
)

_UNIT_CONVERSIONS: dict[str, tuple[Decimal, str]] = {
    "kg": (Decimal("1000000"), "mg"),
    "g": (Decimal("1000"), "mg"),
    "gram": (Decimal("1000"), "mg"),
    "grams": (Decimal("1000"), "mg"),
    "mg": (Decimal("1"), "mg"),
    "milligram": (Decimal("1"), "mg"),
    "milligrams": (Decimal("1"), "mg"),
    "mcg": (Decimal("0.001"), "mg"),
    "ug": (Decimal("0.001"), "mg"),
    "microgram": (Decimal("0.001"), "mg"),
    "micrograms": (Decimal("0.001"), "mg"),
    "l": (Decimal("1000"), "ml"),
    "liter": (Decimal("1000"), "ml"),
    "liters": (Decimal("1000"), "ml"),
    "litre": (Decimal("1000"), "ml"),
    "litres": (Decimal("1000"), "ml"),
    "ml": (Decimal("1"), "ml"),
    "milliliter": (Decimal("1"), "ml"),
    "milliliters": (Decimal("1"), "ml"),
    "millilitre": (Decimal("1"), "ml"),
    "millilitres": (Decimal("1"), "ml"),
}


class MedicineNotFoundError(LookupError):
    """Raised when the requested catalog medicine does not exist."""


@dataclass(frozen=True)
class AlternativeMatch:
    medicine: Medicine
    match_reasons: tuple[str, ...] = MATCH_REASONS


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.casefold().strip().split())
    return normalized or None


def normalize_ingredients(value: str | None) -> tuple[str, ...] | None:
    """Return an order-independent signature for ingredient names."""
    normalized = _normalized_text(value)
    if normalized is None:
        return None
    ingredients = tuple(sorted(
        ingredient
        for ingredient in _INGREDIENT_SEPARATOR.split(normalized)
        if ingredient
    ))
    return ingredients or None


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _normalize_strength_component(component: str) -> str:
    component = component.replace("\u00b5", "u").replace("\u03bc", "u").casefold()

    def replace_amount(match: re.Match[str]) -> str:
        try:
            amount = Decimal(match.group("amount"))
        except InvalidOperation:
            return match.group(0)
        multiplier, canonical_unit = _UNIT_CONVERSIONS[match.group("unit").casefold()]
        return f"{_decimal_text(amount * multiplier)}{canonical_unit}"

    converted = _AMOUNT_WITH_UNIT.sub(replace_amount, component)
    return re.sub(r"\s+", "", converted)


def normalize_strength(value: str | None) -> str | None:
    """Normalize mass/volume units and combination-component ordering."""
    normalized = _normalized_text(value)
    if normalized is None:
        return None
    components = [
        _normalize_strength_component(component)
        for component in _STRENGTH_SEPARATOR.split(normalized)
        if component.strip()
    ]
    return "+".join(sorted(components)) or None


def _comparison_signature(medicine: Medicine) -> tuple[object, ...] | None:
    signature = (
        normalize_ingredients(medicine.active_ingredient),
        normalize_strength(medicine.strength),
        _normalized_text(medicine.dosage_form),
        _normalized_text(medicine.route),
        _normalized_text(medicine.release_type),
    )
    return None if any(value is None for value in signature) else signature


def find_alternatives(
    repository: MedicineRepository,
    medicine_id: int,
) -> list[AlternativeMatch]:
    original = repository.get_by_id(medicine_id)
    if original is None:
        raise MedicineNotFoundError(f"Medicine {medicine_id} was not found")

    original_signature = _comparison_signature(original)
    if original_signature is None:
        return []

    return [
        AlternativeMatch(candidate)
        for candidate in repository.search_by_name("")
        if candidate.id != original.id
        and _comparison_signature(candidate) == original_signature
    ]
