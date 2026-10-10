"""Package extraction, catalog comparison, and verification persistence."""

from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass
from datetime import date, datetime

from sqlmodel import Session

from app.models import Medicine, Patient, Verification
from app.repositories.medicine_repository import MedicineRepository
from app.schemas import VerificationCreateRequest, VerificationFinding
from app.services import gemini_service
from app.services.alternative_service import normalize_strength
from app.services.gemini_service import PackageExtraction
from app.services.image_validation import validate_image


LIMITATIONS = (
    "A record match does not prove that a physical package is authentic. "
    "This check only compares reviewed fields with the available reference data."
)
MIN_CATALOG_COMPARISONS = 2


class VerificationServiceError(RuntimeError):
    """Base error for verification workflows."""


class VerificationPatientNotFoundError(VerificationServiceError):
    """Raised when the verification patient does not exist."""


class VerificationMedicineNotFoundError(VerificationServiceError):
    """Raised when a supplied catalog medicine ID does not exist."""


class VerificationSaveError(VerificationServiceError):
    """Raised after a verification transaction is rolled back."""


from app.services.authenticity import AuthenticityAssessment, assess_authenticity


@dataclass(frozen=True)
class VerificationResult:
    verification: Verification
    findings: tuple[VerificationFinding, ...]
    source: str
    assessment: AuthenticityAssessment | None = None


def extract_package_draft(image_bytes: bytes) -> tuple[PackageExtraction, bool]:
    """Validate and transcribe package fields without judging the package."""
    mime_type = validate_image(image_bytes)
    extraction = gemini_service.extract_package(image_bytes, mime_type)
    return extraction, gemini_service.using_mock_ai()


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.casefold().strip().split())
    return normalized or None


def _find_reference(
    repository: MedicineRepository,
    payload: VerificationCreateRequest,
) -> Medicine | None:
    if _text(payload.registration_number):
        reference = repository.find_by_registration_no(payload.registration_number or "")
        if reference is not None:
            return reference
    if _text(payload.brand_name):
        return repository.find_by_brand_name(payload.brand_name or "")
    return None


def _field_finding(
    field: str,
    reviewed_value: str | None,
    reference_value: str | None,
) -> VerificationFinding:
    display_name = field.replace("_", " ").capitalize()
    if _text(reviewed_value) is None:
        return VerificationFinding(
            field=field,
            result="not_available",
            message=f"{display_name} was not provided from the package",
        )
    if _text(reference_value) is None:
        return VerificationFinding(
            field=field,
            result="not_available",
            message=f"{display_name} is not available in the reference record",
        )

    if field == "strength":
        matches = normalize_strength(reviewed_value) == normalize_strength(reference_value)
    else:
        matches = _text(reviewed_value) == _text(reference_value)

    return VerificationFinding(
        field=field,
        result="match" if matches else "mismatch",
        message=(
            f"{display_name} matches the reference record"
            if matches
            else f"{display_name} differs from the reference record"
        ),
    )


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def parse_expiry_date(value: str | None) -> date | None:
    """Parse common package expiry formats, treating month-only values as month-end."""
    normalized = _text(value)
    if normalized is None:
        return None
    cleaned = re.sub(r"^(?:exp(?:iry)?(?:\s+date)?)[\s:.-]*", "", normalized).strip()

    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(cleaned, pattern).date()
        except ValueError:
            pass

    for pattern in ("%b %Y", "%B %Y", "%m/%Y", "%m-%Y", "%Y-%m"):
        try:
            parsed = datetime.strptime(cleaned, pattern)
            return _last_day(parsed.year, parsed.month)
        except ValueError:
            pass

    if re.fullmatch(r"\d{4}", cleaned):
        year = int(cleaned)
        if 1900 <= year <= 9999:
            return date(year, 12, 31)
    return None


def _expiry_finding(expiry_text: str | None, today: date) -> VerificationFinding:
    parsed = parse_expiry_date(expiry_text)
    if parsed is None:
        return VerificationFinding(
            field="expiry_date",
            result="not_available",
            message=(
                "Expiry date was not provided or could not be interpreted"
            ),
        )
    if parsed < today:
        return VerificationFinding(
            field="expiry_date",
            result="mismatch",
            message=f"The visible expiry date ({expiry_text}) is in the past",
        )
    return VerificationFinding(
        field="expiry_date",
        result="match",
        message=f"The visible expiry date ({expiry_text}) is not in the past",
    )


def verify_package(
    session: Session,
    payload: VerificationCreateRequest,
    *,
    today: date | None = None,
) -> VerificationResult:
    """Compare reviewed fields with the catalog and save the result."""
    if session.get(Patient, payload.patient_id) is None:
        raise VerificationPatientNotFoundError(
            f"Patient {payload.patient_id} does not exist"
        )

    repository = MedicineRepository(session)
    if (
        payload.medicine_id is not None
        and repository.get_by_id(payload.medicine_id) is None
    ):
        raise VerificationMedicineNotFoundError(
            f"Medicine {payload.medicine_id} was not found"
        )
    reference = _find_reference(repository, payload)
    catalog_fields = (
        ("brand_name", payload.brand_name),
        ("manufacturer", payload.manufacturer),
        ("strength", payload.strength),
        ("dosage_form", payload.dosage_form),
    )
    findings = [
        _field_finding(
            field,
            reviewed_value,
            getattr(reference, field) if reference is not None else None,
        )
        for field, reviewed_value in catalog_fields
    ]
    findings.append(_expiry_finding(payload.expiry_date_text, today or date.today()))

    compared = [finding for finding in findings[:4] if finding.result != "not_available"]
    has_conflict = any(finding.result == "mismatch" for finding in findings)

    assessment = assess_authenticity(
        brand_name=payload.brand_name,
        active_ingredient=payload.active_ingredient,
        strength=payload.strength,
        dosage_form=payload.dosage_form,
        manufacturer=payload.manufacturer,
        registration_number=payload.registration_number,
        batch_number=payload.batch_number,
        mfg_date_text=payload.mfg_date_text,
        expiry_date_text=payload.expiry_date_text,
        barcode_or_qr=payload.barcode_or_qr,
        altered_label_flags=payload.altered_label_flags,
        image_quality_issues=payload.image_quality_issues,
        visual_packaging_flags=payload.visual_packaging_flags,
        today=today or date.today(),
    )

    if reference is None:
        if assessment.is_recalled or assessment.is_expired or len(payload.altered_label_flags) > 0:
            status = "inconsistent_information"
            source = "DRAP Rapid Alert / Safety Notice"
        elif assessment.outcome in ("verified_authoritative", "registered_unconfirmed"):
            status = "record_match"
            source = "DRAP (Drug Regulatory Authority of Pakistan)"
        else:
            status = "unable_to_verify"
            source = "demo_dataset"
    elif has_conflict or assessment.is_recalled or len(payload.altered_label_flags) > 0:
        status = "inconsistent_information"
        source = reference.data_source
    elif len(compared) < MIN_CATALOG_COMPARISONS:
        status = "unable_to_verify"
        source = reference.data_source
    else:
        status = "record_match"
        source = reference.data_source

    verification = Verification(
        patient_id=payload.patient_id,
        medicine_id=reference.id if reference is not None else None,
        extracted_details_json=payload.model_dump_json(),
        findings_json=json.dumps([finding.model_dump() for finding in findings]),
        status=status,
        source=source,
    )
    try:
        session.add(verification)
        session.commit()
        session.refresh(verification)
    except Exception as exc:
        session.rollback()
        raise VerificationSaveError("The verification could not be saved") from exc

    return VerificationResult(
        verification=verification,
        findings=tuple(findings),
        source=source,
        assessment=assessment,
    )
