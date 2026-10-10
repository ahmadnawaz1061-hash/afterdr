"""Persistence and PDF generation for medicine concern report drafts."""

from __future__ import annotations

import json
import textwrap
from datetime import timezone
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from sqlmodel import Session

from app.models import Medicine, Report, Verification
from app.schemas import ReportCreateRequest
from app.services.verification_service import LIMITATIONS


DRAFT_LABEL = "DRAFT \u2014 NOT SUBMITTED"
REGULATOR_URL = "https://www.dra.gov.pk/"
SUBMISSION_NOTE = "Follow official regulatory instructions to submit."


class ReportServiceError(RuntimeError):
    """Base error for report operations."""


class ReportVerificationNotFoundError(ReportServiceError):
    """Raised when the source verification does not exist."""


class ReportNotFoundError(ReportServiceError):
    """Raised when a report draft does not exist."""


class ReportSaveError(ReportServiceError):
    """Raised after a report transaction is rolled back."""


def create_report_draft(session: Session, payload: ReportCreateRequest) -> Report:
    verification = session.get(Verification, payload.verification_id)
    if verification is None:
        raise ReportVerificationNotFoundError(
            f"Verification {payload.verification_id} was not found"
        )

    report = Report(
        verification_id=payload.verification_id,
        pharmacy_name=payload.pharmacy_name,
        purchase_date=payload.purchase_date,
        description=payload.description,
        status="draft_not_submitted",
    )
    try:
        session.add(report)
        session.commit()
        session.refresh(report)
        return report
    except Exception as exc:
        session.rollback()
        raise ReportSaveError("The report draft could not be saved") from exc


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _display(value: Any) -> str:
    if value is None:
        return "Not provided"
    text = " ".join(str(value).split())
    return text or "Not provided"


def generate_report_pdf(session: Session, report_id: int) -> bytes:
    report = session.get(Report, report_id)
    if report is None:
        raise ReportNotFoundError(f"Report {report_id} was not found")
    verification = session.get(Verification, report.verification_id)
    if verification is None:
        raise ReportVerificationNotFoundError(
            f"Verification {report.verification_id} was not found"
        )

    details = _json_object(verification.extracted_details_json)
    findings = _json_list(verification.findings_json)
    analysis = _json_object(verification.findings_json) if details.get('schema_version') == 2 else None
    if analysis:
        details = analysis.get('extracted', {})
    medicine = (
        session.get(Medicine, verification.medicine_id)
        if verification.medicine_id is not None
        else None
    )

    buffer = BytesIO()
    document = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    width, height = A4
    left = 54
    y = height - 46

    def footer() -> None:
        document.setFont("Helvetica", 8)
        document.setFillColorRGB(0.2, 0.25, 0.3)
        document.drawString(left, 38, SUBMISSION_NOTE)
        document.setFillColorRGB(0, 0.35, 0.45)
        document.drawString(left, 24, REGULATOR_URL)
        link_width = stringWidth(REGULATOR_URL, "Helvetica", 8)
        document.linkURL(REGULATOR_URL, (left, 21, left + link_width, 34), relative=0)
        document.setFillColorRGB(0, 0, 0)

    def page_header(*, include_title: bool) -> None:
        nonlocal y
        document.setFont("Helvetica-Bold", 13)
        document.drawString(left, height - 46, DRAFT_LABEL)
        if include_title:
            document.setFont("Helvetica-Bold", 16)
            document.drawString(left, height - 75, "AFTER DR \u2014 MEDICINE CONCERN REPORT")
            y = height - 105
        else:
            y = height - 72

    def new_page() -> None:
        footer()
        document.showPage()
        page_header(include_title=False)

    def lines_for(text: str, *, width_chars: int = 92) -> list[str]:
        return textwrap.wrap(
            _display(text),
            width=width_chars,
            replace_whitespace=True,
            drop_whitespace=True,
        ) or ["Not provided"]

    def add_field(label: str, value: Any) -> None:
        nonlocal y
        lines = lines_for(_display(value))
        needed = 31 + max(0, len(lines) - 1) * 13
        if y - needed < 68:
            new_page()
        document.setFont("Helvetica-Bold", 9)
        document.drawString(left, y, f"{label}:")
        y -= 13
        document.setFont("Helvetica", 9)
        value_x = left + 12
        document.drawString(value_x, y, lines[0])
        for line in lines[1:]:
            y -= 13
            document.drawString(value_x, y, line)
        y -= 18

    document.setTitle(f"After Dr report draft {report.id}")
    document.setAuthor("After Dr")
    page_header(include_title=True)

    medicine_name = details.get("brand_name") or (
        medicine.brand_name if medicine is not None else None
    )
    manufacturer = details.get("manufacturer") or (
        medicine.manufacturer if medicine is not None else None
    )
    registration = details.get("registration_number") or (
        medicine.registration_no if medicine is not None else None
    )
    add_field("Medicine name", medicine_name)
    add_field("Manufacturer", manufacturer)
    add_field("Registration number (if visible)", registration)
    if analysis:
        add_field('Verification identifier', verification.id)
        add_field('Assessment status', analysis.get('status_label'))
        add_field('Risk level', analysis.get('risk_level'))
        add_field('Risk score (not an authenticity probability)', analysis.get('risk_score'))
        add_field('Assessment summary', analysis.get('summary'))
        for field in ('active_ingredient', 'strength', 'dosage_form', 'pack_type'):
            add_field(field.replace('_', ' ').title(), details.get(field))
        if analysis.get('simulated'):
            add_field('Evidence mode', 'Simulated demo data; demonstration findings are not regulatory determinations.')
    else:
        # Legacy downloads retain their original contract. The new packaging
        # report intentionally contains none of the former date/batch fields.
        add_field("Batch number", details.get("batch_number"))
        add_field("Expiry date", details.get("expiry_date_text"))
    add_field("Seller / pharmacy", report.pharmacy_name)
    add_field("Purchase date", report.purchase_date.isoformat() if report.purchase_date else None)
    add_field("Observed concerns", report.description)
    add_field("Reference data source", verification.source)

    evidence = [
        f"{_display(item.get('field')).replace('_', ' ').title()}: "
        f"{_display(item.get('result')).upper()} \u2014 {_display(item.get('message'))}"
        for item in findings
    ]
    if analysis:
        for signal in analysis.get('signals', []):
            add_field(f"Evidence: {signal.get('title', 'Observation')}", f"{signal.get('severity')} | {signal.get('origin')} | {signal.get('detail')}")
        reference = analysis.get('matched_reference')
        online = analysis.get('online_lookup')
        if online:
            add_field('Internet product lookup', online.get('status'))
            add_field('Online comparison', online.get('summary'))
            if isinstance(online.get('product'), dict):
                for key in ('brand_name', 'manufacturer', 'active_ingredient', 'strength', 'dosage_form'):
                    add_field('Online ' + key.replace('_', ' '), online['product'].get(key))
            for source in online.get('sources', []):
                add_field('Internet source', f"{source.get('title')} | {source.get('url')}")
        if reference:
            add_field('Available reference comparison', f"{reference.get('brand_name')} | {reference.get('manufacturer')} | {reference.get('data_source')} | {reference.get('comparison_status')}")
            add_field('Reference source', reference.get('source_url'))
        add_field('Registration comparison', analysis.get('registration_state'))
        add_field('Recommended next steps', ' | '.join(analysis.get('next_steps', [])))
    else:
        add_field("Supporting evidence", " | ".join(evidence) if evidence else None)
    generated_at = report.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    add_field("Report generated on", generated_at)
    add_field("Limitations", ' | '.join(analysis.get('limitations', [])) if analysis else LIMITATIONS)

    footer()
    document.save()
    return buffer.getvalue()
