"""Module C's offline DRAP catalog and provenance; no network or patient writes."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.models import Medicine


CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "alternative_medicines_pk.json"
MEDICINE_FIELDS = (
    "brand_name", "active_ingredient", "strength", "dosage_form", "route",
    "release_type", "manufacturer", "registration_no", "data_source",
)


def _official_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and (
        parsed.hostname == "dra.gov.pk" or parsed.hostname.endswith(".dra.gov.pk")
    ) and not parsed.username and not parsed.password


def _formulation_url(value: str) -> bool:
    parsed = urlsplit(value)
    return _official_url(value) or (
        parsed.scheme == "https" and parsed.hostname == "getzpharma.com"
        and parsed.path == "/wp-content/uploads/2023/03/Getzid-MR-Range-Leaflet-PAK.pdf"
        and not parsed.username and not parsed.password
    )


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if catalog.get("catalog") != "drap_pk" or not catalog.get("records"):
        raise ValueError("Module C requires a nonempty Pakistan/DRAP catalog")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", catalog.get("source_checked_at", "")):
        raise ValueError("Catalog must declare a source check date")
    registrations = set()
    for record in catalog["records"]:
        if any(not isinstance(record.get(field), str) or not record[field].strip() for field in MEDICINE_FIELDS):
            raise ValueError("Catalog fields must be explicit; use 'unknown' for undocumented attributes")
        registration = record["registration_no"]
        if record["data_source"] != "drap_pk" or not re.fullmatch(r"\d{6}", registration):
            raise ValueError("Catalog records require a documented DRAP registration number")
        if registration in registrations:
            raise ValueError(f"Duplicate DRAP registration {registration}")
        registrations.add(registration)
        if not _official_url(record.get("source_url", "")):
            raise ValueError("Catalog evidence must link to an official DRAP HTTPS page")
        if record.get("formulation_source_url") and not _formulation_url(record["formulation_source_url"]):
            raise ValueError("Formulation evidence must link to DRAP or a reviewed Pakistan manufacturer leaflet")
        if record["route"] != "unknown" or record["release_type"] != "unknown":
            if not record.get("formulation_source_url") or not record.get("evidence_note"):
                raise ValueError("Documented route/release attributes need formulation evidence")
    return catalog


def provenance(medicine: Medicine) -> dict:
    if medicine.data_source != "drap_pk":
        return {}
    catalog = load_catalog()
    for record in catalog["records"]:
        if all(getattr(medicine, field) == record[field] for field in MEDICINE_FIELDS):
            return {
                "source_url": record["source_url"],
                "source_checked_at": record.get("source_checked_at", catalog["source_checked_at"]),
                "formulation_source_url": record.get("formulation_source_url"),
                "source_search_query": record.get("source_search_query"),
            }
    return {}


def import_catalog(session: Session) -> tuple[int, int]:
    """Insert missing records; preserve existing records and all patient data.

    Conflicting registrations fail before committing any additions. Matching
    records are skipped so the command can safely be rerun.
    """
    inserted = skipped = 0
    try:
        for record in load_catalog()["records"]:
            existing = session.exec(select(Medicine).where(Medicine.registration_no == record["registration_no"])).all()
            if existing:
                if len(existing) != 1 or any(getattr(existing[0], field) != record[field] for field in MEDICINE_FIELDS):
                    raise ValueError(f"Registration {record['registration_no']} conflicts with an existing catalog record; review it before importing")
                skipped += 1
                continue
            session.add(Medicine(**{field: record[field] for field in MEDICINE_FIELDS}))
            inserted += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    return inserted, skipped
