"""Deterministic catalog matching for potential medicine alternatives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

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
_NUMBER = r"(?:\d+(?:\.\d+)?|\.\d+)"
_STRENGTH_COMPONENT = re.compile(
    rf"(?P<amount>{_NUMBER})\s*"
    r"(?P<unit>milligrams?|micrograms?|grams?|mcg|mg|kg|ug|g)"
    rf"(?:\s*/\s*(?P<volume>{_NUMBER})?\s*"
    r"(?P<volume_unit>millilit(?:er|re)s?|lit(?:er|re)s?|ml|l))?",
    re.IGNORECASE,
)
_UNKNOWN_VALUES = frozenset({
    "unknown", "unspecified", "not provided", "not available", "n/a", "na", "none", "null", "?", "-",
})

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
    return normalized if normalized and normalized not in _UNKNOWN_VALUES else None


def _ingredient_names(value: str | None) -> tuple[str, ...] | None:
    normalized = _normalized_text(value)
    if normalized is None:
        return None
    ingredients = tuple(_INGREDIENT_SEPARATOR.split(normalized))
    if any(_normalized_text(name) is None for name in ingredients):
        return None
    # Duplicate names make positional strength assignment ambiguous.
    return ingredients if len(set(ingredients)) == len(ingredients) else None


def normalize_ingredients(value: str | None) -> tuple[str, ...] | None:
    """Normalize exact catalog identities; never infer salts or synonyms."""
    names = _ingredient_names(value)
    return tuple(sorted(names)) if names else None


def _normalize_strength_component(component: str) -> str | None:
    component = component.replace("\u00b5", "u").replace("\u03bc", "u").casefold()
    match = _STRENGTH_COMPONENT.fullmatch(component.strip())
    if match is None:
        return None
    amount = Fraction(Decimal(match.group("amount")))
    if amount <= 0:
        return None
    multiplier, _unit = _UNIT_CONVERSIONS[match.group("unit")]
    amount *= Fraction(multiplier)
    suffix = "mg"
    if match.group("volume_unit"):
        volume = Fraction(Decimal(match.group("volume") or "1"))
        if volume <= 0:
            return None
        volume_multiplier, _unit = _UNIT_CONVERSIONS[match.group("volume_unit")]
        amount /= volume * Fraction(volume_multiplier)
        suffix = "mg/ml"
    # Exact fractions avoid rounding two different concentrations into a match.
    denominator = amount.denominator
    if denominator == 1:
        number = str(amount.numerator)
    else:
        # Finite decimal output retains the existing public normalization format.
        finite = denominator
        for factor in (2, 5):
            while finite % factor == 0:
                finite //= factor
        if finite == 1:
            from decimal import localcontext

            with localcontext() as context:
                context.prec = len(str(amount.numerator)) + len(str(denominator)) * 4 + 10
                number = format(Decimal(amount.numerator) / Decimal(denominator), "f").rstrip("0").rstrip(".")
        else:
            number = f"{amount.numerator}/{denominator}"
    return f"{number}{suffix}"


def normalize_matching_strength(value: str | None) -> str | None:
    """Normalize positive mass amounts/concentrations, preserving ingredient order.

    Unsupported notation (percent, IU, labeled or shared-denominator mixtures)
    is excluded rather than guessed. Each component must be fully parseable.
    """
    normalized = _normalized_text(value)
    if normalized is None:
        return None
    components = [
        _normalize_strength_component(component)
        for component in _STRENGTH_SEPARATOR.split(normalized)
    ]
    if not components or any(component is None for component in components):
        return None
    if len({component.endswith("/ml") for component in components}) > 1:
        return None
    return "+".join(components)


def normalize_strength(value: str | None) -> str | None:
    """Preserve the existing public helper used by the authenticity module.

    This legacy text normalization is not evidence for substitution. Module C
    uses normalize_matching_strength, which rejects ambiguous notation instead.
    Retaining unrecognized text here prevents two distinct unsupported values
    from becoming equal merely because both failed the stricter parser.
    """
    if value is None:
        return None
    normalized = " ".join(value.casefold().strip().split())
    if not normalized:
        return None

    def replace_amount(match: re.Match[str]) -> str:
        try:
            amount = Decimal(match.group("amount"))
        except InvalidOperation:
            return match.group(0)
        multiplier, canonical_unit = _UNIT_CONVERSIONS[match.group("unit").casefold()]
        text = format((amount * multiplier).normalize(), "f")
        text = text.rstrip("0").rstrip(".") if "." in text else text
        return f"{text}{canonical_unit}"

    components = []
    for component in _STRENGTH_SEPARATOR.split(normalized):
        if component.strip():
            component = component.replace("\u00b5", "u").replace("\u03bc", "u")
            components.append(re.sub(r"\s+", "", _AMOUNT_WITH_UNIT.sub(replace_amount, component)))
    return "+".join(sorted(components)) or None


def _comparison_signature(medicine: Medicine) -> tuple[object, ...] | None:
    ingredients = _ingredient_names(medicine.active_ingredient)
    strength = normalize_matching_strength(medicine.strength)
    if ingredients is None or strength is None:
        return None
    strengths = strength.split("+")
    if len(ingredients) != len(strengths):
        return None
    if _normalized_text(medicine.brand_name) is None or _normalized_text(medicine.data_source) is None:
        return None
    signature = (
        # Bind each amount to its own ingredient before sorting the pairs.
        tuple(sorted(zip(ingredients, strengths))),
        _normalized_text(medicine.dosage_form),
        _normalized_text(medicine.route),
        _normalized_text(medicine.release_type),
        _normalized_text(medicine.data_source) == "demo_dataset",
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
