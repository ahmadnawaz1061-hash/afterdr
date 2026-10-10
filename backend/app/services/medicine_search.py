"""Tolerant name lookup only; never used to decide medicine equivalence."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from app.models import Medicine


def normalize_query(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold()
    value = re.sub(r'(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)', ' ', value)
    # Preserve decimal strengths: 2.5 mg must not turn into 2 mg + 5 mg.
    tokens = re.findall(r'\d+(?:\.\d+)?|\.\d+|[^\W\d_]+', value, flags=re.UNICODE)
    value = ' '.join('0' + token if token.startswith('.') else token for token in tokens)
    for alias, canonical in {
        'acetaminophen': 'paracetamol', 'amoxycillin': 'amoxicillin',
        'acetyl salicylic acid': 'aspirin', 'acetylsalicylic acid': 'aspirin',
        'hcl': 'hydrochloride', 'tablets': 'tablet', 'tabs': 'tablet',
        'tab': 'tablet', 'capsules': 'capsule', 'caps': 'capsule',
    }.items():
        value = re.sub(rf'\b{alias}\b', canonical, value)
    return value


def _distance(left: str, right: str) -> int:
    """Edit distance including a neighboring-letter transposition."""
    rows = [list(range(len(right) + 1))]
    for i, char in enumerate(left, 1):
        row = [i]
        for j, other in enumerate(right, 1):
            cost = char != other
            value = min(rows[-1][j] + 1, row[-1] + 1, rows[-1][j - 1] + cost)
            if i > 1 and j > 1 and char == right[j - 2] and left[i - 2] == other:
                value = min(value, rows[-2][j - 2] + 1)
            row.append(value)
        rows.append(row)
    return rows[-1][-1]


@dataclass(frozen=True)
class SearchMatch:
    medicine: Medicine
    similar_spelling: bool = False


def rank_medicines(medicines: list[Medicine], query: str) -> list[SearchMatch]:
    term = normalize_query(query)
    ordered = sorted(medicines, key=lambda m: (m.brand_name.casefold(), m.id or 0))
    if not query.strip():
        return [SearchMatch(m) for m in ordered]
    if not term:
        return []
    exact, approximate = [], []
    for medicine in ordered:
        names = [normalize_query(medicine.brand_name), normalize_query(medicine.active_ingredient)]
        combined = normalize_query(f'{medicine.brand_name} {medicine.active_ingredient} {medicine.strength} {medicine.dosage_form}')
        tokens = combined.split()
        # Never fuzzy-match a dose or let a substring match 50 to 500.
        if any(word not in tokens for word in term.split() if any(char.isdigit() for char in word)):
            continue
        score = max((100 if term == name else 90 if name.startswith(term) else 80 if term in name else 0) for name in names)
        if not score and all(word in tokens for word in term.split()):
            score = 70
        if score:
            exact.append((score, medicine))
            continue
        total_distance = 0
        for word in term.split():
            if word in tokens:
                continue
            # Numbers/units must match exactly; short queries are not fuzzy.
            allowance = 0 if len(word) < 4 or not word.isalpha() else 1 if len(word) < 8 else 2
            candidates = [token for name in names for token in name.split()
                          if token.isalpha() and abs(len(word) - len(token)) <= allowance]
            distance = min((_distance(word, token) for token in candidates), default=100)
            if distance > allowance:
                break
            total_distance += distance
        else:
            approximate.append((total_distance, medicine))
    # Do not dilute an exact search with unrelated lookalike medicine names.
    if exact:
        return [SearchMatch(m) for _, m in sorted(exact, key=lambda pair: -pair[0])]
    return [SearchMatch(m, True) for _, m in sorted(approximate, key=lambda pair: pair[0])]
