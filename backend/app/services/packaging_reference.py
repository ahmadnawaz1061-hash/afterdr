"""Offline, sourced product comparisons; no live registry or synthetic records."""
import csv
from difflib import SequenceMatcher
from pathlib import Path
import re
from urllib.parse import urlsplit
from app.services.alternative_service import normalize_matching_strength

REFERENCE_PATH = Path(__file__).resolve().parents[2] / 'data/known_brands.csv'


def normalize_name(value):
    return ' '.join(re.findall(r'[a-z0-9]+', (value or '').casefold()))


def brand_key(value):
    value = normalize_name(value)
    # Remove a product's strength/form descriptors, preserving meaningful
    # suffixes (Extra, MR, XR, DS) and never removing arbitrary brand words.
    return re.split(r'\b(?:tablets?|capsules?|suspension|syrup|drops|injection|infusion|granules|sachet|\d)', value, maxsplit=1)[0].strip()


def normalize_form(value):
    return re.sub(r'\b(tablets|capsules)\b', lambda match: match.group(1)[:-1], normalize_name(value))


def similarity(left, right):
    return SequenceMatcher(None, normalize_name(left), normalize_name(right)).ratio()


def normalize_manufacturer(value):
    text = normalize_name(value)
    for word in ('private', 'pvt', 'limited', 'ltd', 'inc', 'company', 'co'):
        text = re.sub(rf'\b{word}\b', '', text)
    return ' '.join(text.split())


def manufacturer_matches(left, right):
    left, right = normalize_manufacturer(left), normalize_manufacturer(right)
    if not left or not right:
        return False
    if left == right:
        return True
    # Explicit common printed company abbreviations; no fuzzy supplier match.
    aliases = {'abbott': 'abbott laboratories pakistan',
               'gsk': 'glaxosmithkline pakistan',
               'glaxosmithkline': 'glaxosmithkline pakistan'}
    return aliases.get(left, left) == aliases.get(right, right)


def load_brand_references(path=None):
    path = Path(path) if path else REFERENCE_PATH
    if not path.exists():
        return []
    records = []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            row = {key: (value or '').strip() or None for key, value in row.items() if key}
            if not row.get('brand_name') or row.get('data_source') not in {'drap_pk', 'manufacturer_documented'}:
                continue
            parsed = urlsplit(row.get('source_url') or '')
            if parsed.scheme != 'https' or parsed.username or parsed.password or not parsed.hostname:
                continue
            if row['data_source'] == 'drap_pk' and not (parsed.hostname == 'dra.gov.pk' or parsed.hostname.endswith('.dra.gov.pk')):
                continue
            # Manufacturer entries require an explicit manually reviewed URL;
            # no entries are generated dynamically or retrieved at runtime.
            records.append(row)
    return records


def find_brand_reference(fields, records=None):
    records = load_brand_references() if records is None else records
    brand = brand_key(fields.brand_name)
    if not brand:
        return None, None, 0, False
    candidates = []
    for row in records:
        aliases = [brand_key(alias) for alias in (row.get('aliases') or '').split('|') if alias.strip()]
        key = brand_key(row['brand_name'])
        ratio = similarity(brand, key)
        kind = 'exact' if brand == key else 'alias' if brand in aliases else 'lookalike'
        if kind == 'lookalike' and (len(brand) < 5 or len(key) < 5 or ratio < .72):
            continue
        if kind == 'alias':
            ratio = 1.0
        corroboration = 0
        if fields.manufacturer and manufacturer_matches(fields.manufacturer, row.get('manufacturer')):
            corroboration += 2
        visible_strength = normalize_matching_strength(fields.strength)
        reference_strength = normalize_matching_strength(row.get('strength'))
        if visible_strength is not None and visible_strength == reference_strength:
            corroboration += 2
        if fields.dosage_form and normalize_form(fields.dosage_form) in normalize_form(row.get('dosage_form')):
            corroboration += 1
        candidates.append((0 if kind in {'exact', 'alias'} else 1, -ratio, -corroboration, row, kind))
    if not candidates:
        return None, None, 0, False
    candidates.sort(key=lambda item: item[:3])
    first = candidates[0]
    same = [item for item in candidates if item[:3] == first[:3]]
    matching_reg = next((item for item in same if fields.registration_number and normalize_name(item[3].get('registration_no')) == normalize_name(fields.registration_number)), None)
    selected = matching_reg or first
    unambiguous = len(same) == 1 or matching_reg is not None or len({item[3].get('registration_no') for item in same}) == 1
    return selected[3], selected[4], round(-selected[1], 4), unambiguous and selected[4] in {'exact', 'alias'}
