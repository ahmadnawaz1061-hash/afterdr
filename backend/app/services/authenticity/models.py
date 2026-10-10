"""Data models for Pakistan medicine authenticity assessment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

AuthenticityOutcome = Literal[
    "verified_authoritative",
    "registered_unconfirmed",
    "potentially_suspicious",
    "possible_recall",
    "expired",
    "inconclusive",
]


@dataclass(frozen=True)
class EvidenceItem:
    category: str
    source: str
    detail: str
    is_critical: bool = False
    source_url: str | None = None


@dataclass(frozen=True)
class DrapRegisteredProduct:
    registration_no: str
    brand_name: str
    active_ingredient: str
    strength: str
    dosage_form: str
    manufacturer: str
    pack_size: str | None = None
    status: str = "Active"
    source_url: str = "https://www.dra.gov.pk/"


@dataclass(frozen=True)
class DrapRecallAlert:
    alert_id: str
    alert_date: str
    brand_name: str
    batch_numbers: tuple[str, ...]
    manufacturer: str
    reason: str
    classification: str
    advisory: str
    source_url: str = "https://www.dra.gov.pk/safety-alerts/"


@dataclass(frozen=True)
class AuthenticityAssessment:
    outcome: AuthenticityOutcome
    outcome_label: str
    summary_message: str
    is_expired: bool
    is_recalled: bool
    discrepancies: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]
    recommended_next_steps: tuple[str, ...]
    disclaimer: str
    source_links: tuple[dict[str, str], ...]
    assessed_at: str
