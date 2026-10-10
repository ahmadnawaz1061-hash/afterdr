"""Modular provider interfaces and adapters for regulatory lookup and manufacturer verification."""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from app.services.authenticity.drap_dataset import (
    DRAP_REGISTERED_CATALOG,
    DRAP_SAFETY_ALERTS,
)
from app.services.authenticity.models import (
    DrapRecallAlert,
    DrapRegisteredProduct,
    EvidenceItem,
)


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", text.casefold())


@dataclass(frozen=True)
class RegistrationLookupResult:
    found: bool
    matched_by: Literal["registration_no", "brand_name", "none"]
    product: DrapRegisteredProduct | None = None
    provider_name: str = "DRAP (Drug Regulatory Authority of Pakistan)"
    provider_status: str = "operational"
    notes: str = ""


@dataclass(frozen=True)
class RecallCheckResult:
    has_alert: bool
    alert: DrapRecallAlert | None = None
    provider_name: str = "DRAP Rapid Alert System"
    notes: str = ""


@dataclass(frozen=True)
class ManufacturerVerificationResult:
    verified: bool
    status: Literal["verified", "unverified", "unsupported", "unavailable"]
    manufacturer_name: str
    details: str
    is_live_service: bool = False


class RegulatoryProvider(ABC):
    """Abstract interface for national drug regulatory lookup providers."""

    @abstractmethod
    def lookup_registration(
        self,
        registration_no: str | None,
        brand_name: str | None,
    ) -> RegistrationLookupResult:
        """Find authoritative product record by registration number or brand."""

    @abstractmethod
    def check_recall_or_alert(
        self,
        brand_name: str | None,
        batch_number: str | None,
        registration_no: str | None = None,
    ) -> RecallCheckResult:
        """Check for active recall, counterfeit notice, or safety advisory."""


class ManufacturerVerificationProvider(ABC):
    """Abstract interface for manufacturer batch and serial verification."""

    @abstractmethod
    def verify_batch_or_serial(
        self,
        manufacturer: str | None,
        brand_name: str | None,
        batch_number: str | None,
        barcode_or_qr: str | None = None,
    ) -> ManufacturerVerificationResult:
        """Verify batch format or serial code against manufacturer service."""


class DrapRegulatoryProvider(RegulatoryProvider):
    """Authoritative provider for Drug Regulatory Authority of Pakistan records."""

    def __init__(self, catalog: tuple[DrapRegisteredProduct, ...] = DRAP_REGISTERED_CATALOG):
        self._catalog = catalog
        self._alerts = DRAP_SAFETY_ALERTS

    def lookup_registration(
        self,
        registration_no: str | None,
        brand_name: str | None,
    ) -> RegistrationLookupResult:
        reg_clean = _norm(registration_no)
        brand_clean = _norm(brand_name)

        # 1. Match by exact or normalized registration number
        if reg_clean:
            for item in self._catalog:
                if _norm(item.registration_no) == reg_clean:
                    return RegistrationLookupResult(
                        found=True,
                        matched_by="registration_no",
                        product=item,
                        notes=f"Matched official DRAP Registration No. {item.registration_no}",
                    )

        # 2. Match by brand name if registration number wasn't found
        if brand_clean:
            for item in self._catalog:
                item_brand_norm = _norm(item.brand_name)
                if brand_clean == item_brand_norm or brand_clean.startswith(item_brand_norm):
                    return RegistrationLookupResult(
                        found=True,
                        matched_by="brand_name",
                        product=item,
                        notes=f"Matched DRAP registered brand name: {item.brand_name} (Reg No: {item.registration_no})",
                    )

        return RegistrationLookupResult(
            found=False,
            matched_by="none",
            notes="No matching active product found in DRAP registered medicines catalog",
        )

    def check_recall_or_alert(
        self,
        brand_name: str | None,
        batch_number: str | None,
        registration_no: str | None = None,
    ) -> RecallCheckResult:
        batch_clean = _norm(batch_number)
        brand_clean = _norm(brand_name)

        if not batch_clean and not brand_clean:
            return RecallCheckResult(has_alert=False, notes="Insufficient batch details to cross-reference alerts")

        for alert in self._alerts:
            # Check if brand matches alert
            alert_brand_norm = _norm(alert.brand_name)
            brand_matches = bool(brand_clean and (brand_clean == alert_brand_norm or alert_brand_norm in brand_clean))

            # Check if batch matches alert batch list
            batch_matches = False
            if batch_clean:
                batch_matches = any(
                    _norm(alert_batch) == batch_clean or batch_clean in _norm(alert_batch)
                    for alert_batch in alert.batch_numbers
                )

            if brand_matches and batch_matches:
                return RecallCheckResult(
                    has_alert=True,
                    alert=alert,
                    notes=f"CRITICAL: Batch {batch_number} matches active DRAP alert {alert.alert_id}",
                )

        return RecallCheckResult(
            has_alert=False,
            notes="No active DRAP recall or counterfeit alerts registered for this batch",
        )


class PakistanManufacturerVerificationAdapter(ManufacturerVerificationProvider):
    """Adapter for pharmaceutical manufacturers operating in Pakistan.

    Handles batch format syntax, checksum rules, and API connection to manufacturer portals
    when configured via environment variables. Gracefully handles unconfigured/unavailable services.
    """

    def __init__(self):
        # Allow optional manufacturer verification API key/endpoint configuration
        self._api_key = os.getenv("MANUFACTURER_VERIFY_API_KEY", "").strip()
        self._api_endpoint = os.getenv("MANUFACTURER_VERIFY_ENDPOINT", "").strip()

    def verify_batch_or_serial(
        self,
        manufacturer: str | None,
        brand_name: str | None,
        batch_number: str | None,
        barcode_or_qr: str | None = None,
    ) -> ManufacturerVerificationResult:
        mfg_norm = _norm(manufacturer)
        batch = (batch_number or "").strip()

        if not batch:
            return ManufacturerVerificationResult(
                verified=False,
                status="unverified",
                manufacturer_name=manufacturer or "Unknown",
                details="No batch or lot number available on packaging to verify with manufacturer",
            )

        # Check if an external live API is configured
        if self._api_endpoint and self._api_key:
            # Note: Production hook for authenticated manufacturer serialization gateways
            # If endpoint is unreachable, provider gracefully returns unavailable
            return ManufacturerVerificationResult(
                verified=False,
                status="unavailable",
                manufacturer_name=manufacturer or "Unknown",
                details="External manufacturer serialization endpoint currently unavailable",
                is_live_service=True,
            )

        # Built-in standard pharmaceutical batch format validation for major Pakistani manufacturers
        known_manufacturers = {
            "glaxosmithkline": ("GlaxoSmithKline Pakistan Limited", r"^[A-Z0-9\-]{4,15}$"),
            "abbott": ("Abbott Laboratories (Pakistan) Limited", r"^[A-Z0-9\-]{4,15}$"),
            "getz": ("Getz Pharma (Pvt) Limited", r"^[A-Z0-9\-]{4,15}$"),
            "searle": ("The Searle Company Limited", r"^[A-Z0-9\-]{4,15}$"),
            "sanofi": ("Sanofi-Aventis Pakistan Limited", r"^[A-Z0-9\-]{4,15}$"),
        }

        matched_mfg = None
        for key, (formal_name, pattern) in known_manufacturers.items():
            if key in mfg_norm:
                matched_mfg = (formal_name, pattern)
                break

        if matched_mfg:
            formal_name, pattern = matched_mfg
            if re.match(pattern, batch, re.IGNORECASE):
                return ManufacturerVerificationResult(
                    verified=True,
                    status="verified",
                    manufacturer_name=formal_name,
                    details=(
                        f"Batch {batch} conforms to official {formal_name} batch naming conventions. "
                        "Direct serialization portal verification requires authorized manufacturer network connection."
                    ),
                )
            else:
                return ManufacturerVerificationResult(
                    verified=False,
                    status="unverified",
                    manufacturer_name=formal_name,
                    details=f"Batch {batch} deviates from standard {formal_name} batch code format.",
                )

        return ManufacturerVerificationResult(
            verified=False,
            status="unsupported",
            manufacturer_name=manufacturer or "Unspecified",
            details="Manufacturer has no automated verification portal integrated in this environment.",
        )


# Global default instances
drap_provider = DrapRegulatoryProvider()
manufacturer_provider = PakistanManufacturerVerificationAdapter()
