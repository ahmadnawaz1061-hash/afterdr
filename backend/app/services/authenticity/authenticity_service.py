"""Medicine Authenticity Assessment Engine prioritizing Pakistan and DRAP."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Sequence

from app.services.authenticity.models import (
    AuthenticityAssessment,
    AuthenticityOutcome,
    EvidenceItem,
)
from app.services.authenticity.providers import (
    DrapRegulatoryProvider,
    PakistanManufacturerVerificationAdapter,
    drap_provider as default_drap_provider,
    manufacturer_provider as default_mfg_provider,
)

CORE_SAFETY_DISCLAIMER = (
    "A photograph, packaging inspection, or registration number match cannot prove that a physical "
    "medicine is authentic or therapeutically active. Chemical laboratory analysis is the only definitive test. "
    "Never consume suspected or recalled medicines. Always consult a licensed pharmacist or contact the Drug "
    "Regulatory Authority of Pakistan (DRAP) if you observe any discrepancy."
)


def _clean(val: str | None) -> str:
    if not val:
        return ""
    return " ".join(val.strip().split())


def _parse_mfg_or_exp(text: str | None) -> date | None:
    from app.services.verification_service import parse_expiry_date
    return parse_expiry_date(text)


def assess_authenticity(
    *,
    brand_name: str | None,
    active_ingredient: str | None = None,
    strength: str | None = None,
    dosage_form: str | None = None,
    manufacturer: str | None = None,
    registration_number: str | None = None,
    batch_number: str | None = None,
    mfg_date_text: str | None = None,
    expiry_date_text: str | None = None,
    barcode_or_qr: str | None = None,
    altered_label_flags: Sequence[str] = (),
    image_quality_issues: Sequence[str] = (),
    visual_packaging_flags: Sequence[str] = (),
    today: date | None = None,
    drap_service: DrapRegulatoryProvider | None = None,
    mfg_service: PakistanManufacturerVerificationAdapter | None = None,
) -> AuthenticityAssessment:
    """Evaluate packaging details against Pakistan regulatory sources and physical packaging markers."""
    today = today or date.today()
    drap = drap_service or default_drap_provider
    mfg = mfg_service or default_mfg_provider

    evidence: list[EvidenceItem] = []
    discrepancies: list[str] = []
    source_links: list[dict[str, str]] = [
        {"title": "Drug Regulatory Authority of Pakistan (DRAP)", "url": "https://www.dra.gov.pk/"},
        {"title": "DRAP Rapid Alert & Recalls", "url": "https://www.dra.gov.pk/safety-alerts/"},
    ]

    # --- 1. Check Image Quality & Visual Anomaly Flags ---
    for issue in image_quality_issues:
        evidence.append(EvidenceItem(
            category="image_quality",
            source="Image Processing OCR",
            detail=f"Image quality limitation: {issue}",
            is_critical=False,
        ))

    for flag in altered_label_flags:
        discrepancies.append(f"Visual packaging alert: {flag}")
        evidence.append(EvidenceItem(
            category="visual_anomaly",
            source="Package Visual Inspection",
            detail=flag,
            is_critical=True,
        ))

    for flag in visual_packaging_flags:
        discrepancies.append(f"Physical marker: {flag}")
        evidence.append(EvidenceItem(
            category="visual_anomaly",
            source="Package Visual Inspection",
            detail=flag,
            is_critical=True,
        ))

    # --- 2. Expiry & Manufacturing Date Checks ---
    is_expired = False
    parsed_exp = _parse_mfg_or_exp(expiry_date_text)
    if parsed_exp is not None:
        if parsed_exp < today:
            is_expired = True
            discrepancies.append(f"Package expiry date ({expiry_date_text}) has lapsed (Expired: {parsed_exp.isoformat()})")
            evidence.append(EvidenceItem(
                category="expiry",
                source="Package Expiry Marking",
                detail=f"Expired on {parsed_exp.isoformat()} (before current date {today.isoformat()})",
                is_critical=True,
            ))
        else:
            evidence.append(EvidenceItem(
                category="expiry",
                source="Package Expiry Marking",
                detail=f"Expiry date is in the future ({expiry_date_text})",
                is_critical=False,
            ))
    elif expiry_date_text:
        discrepancies.append(f"Uninterpretable expiry date text: '{expiry_date_text}'")

    parsed_mfg = _parse_mfg_or_exp(mfg_date_text)
    if parsed_mfg is not None:
        if parsed_mfg > today:
            discrepancies.append(f"Manufacturing date ({mfg_date_text}) is in the future ({parsed_mfg.isoformat()})")
            evidence.append(EvidenceItem(
                category="manufacturing_date",
                source="Package Manufacturing Marking",
                detail=f"Inconsistent future manufacturing date ({parsed_mfg.isoformat()})",
                is_critical=True,
            ))
        elif parsed_exp is not None and parsed_mfg >= parsed_exp:
            discrepancies.append(f"Manufacturing date ({mfg_date_text}) cannot be on or after expiry date ({expiry_date_text})")
            evidence.append(EvidenceItem(
                category="manufacturing_date",
                source="Package Timeline Analysis",
                detail=f"Invalid date sequence: MFG {parsed_mfg.isoformat()} >= EXP {parsed_exp.isoformat()}",
                is_critical=True,
            ))

    # --- 3. DRAP Safety Alerts & Counterfeit Recalls ---
    recall_result = drap.check_recall_or_alert(
        brand_name=brand_name,
        batch_number=batch_number,
        registration_no=registration_number,
    )
    is_recalled = recall_result.has_alert
    if is_recalled and recall_result.alert:
        alert = recall_result.alert
        discrepancies.append(
            f"CRITICAL RECALL ALERT ({alert.alert_id}): {alert.reason} (Batch {batch_number})"
        )
        evidence.append(EvidenceItem(
            category="safety_recall",
            source="DRAP Rapid Alert System",
            detail=f"{alert.classification} - {alert.reason}. Advisory: {alert.advisory}",
            is_critical=True,
            source_url=alert.source_url,
        ))
        source_links.append({"title": f"Official Alert: {alert.alert_id}", "url": alert.source_url})

    # --- 4. DRAP Regulatory Registration Lookup ---
    reg_lookup = drap.lookup_registration(
        registration_no=registration_number,
        brand_name=brand_name,
    )

    if reg_lookup.found and reg_lookup.product:
        prod = reg_lookup.product
        evidence.append(EvidenceItem(
            category="regulatory_registration",
            source="DRAP Registered Products Catalog",
            detail=(
                f"DRAP Registration #{prod.registration_no}: {prod.brand_name} ({prod.strength}, {prod.dosage_form}), "
                f"Active Ingredient: {prod.active_ingredient}, Manufacturer: {prod.manufacturer}."
            ),
            is_critical=False,
            source_url=prod.source_url,
        ))

        # Check for field mismatches against official DRAP record
        if manufacturer:
            mfg_clean = _clean(manufacturer).casefold()
            ref_mfg_clean = _clean(prod.manufacturer).casefold()
            if mfg_clean not in ref_mfg_clean and ref_mfg_clean not in mfg_clean:
                discrepancies.append(
                    f"Manufacturer mismatch: Packaging specifies '{manufacturer}', but DRAP registration #{prod.registration_no} is registered to '{prod.manufacturer}'"
                )
                evidence.append(EvidenceItem(
                    category="regulatory_mismatch",
                    source="DRAP Registration Comparison",
                    detail=f"Declared manufacturer '{manufacturer}' differs from registered '{prod.manufacturer}'",
                    is_critical=True,
                ))

        if active_ingredient:
            ing_clean = re.sub(r"[^a-z0-9]", "", active_ingredient.casefold())
            ref_ing_clean = re.sub(r"[^a-z0-9]", "", prod.active_ingredient.casefold())
            if ing_clean not in ref_ing_clean and ref_ing_clean not in ing_clean:
                discrepancies.append(
                    f"Active ingredient discrepancy: Packaging states '{active_ingredient}', while DRAP registry states '{prod.active_ingredient}'"
                )

        if strength and prod.strength:
            from app.services.alternative_service import normalize_strength
            s_pack = normalize_strength(strength)
            s_reg = normalize_strength(prod.strength)
            if s_pack and s_reg and s_pack != s_reg:
                discrepancies.append(
                    f"Strength difference: Packaging displays '{strength}', but DRAP registration is for '{prod.strength}'"
                )
    else:
        evidence.append(EvidenceItem(
            category="regulatory_registration",
            source="DRAP Registration Lookup",
            detail=reg_lookup.notes,
            is_critical=False,
        ))

    # --- 5. Manufacturer Batch Validation ---
    mfg_result = mfg.verify_batch_or_serial(
        manufacturer=manufacturer or (reg_lookup.product.manufacturer if reg_lookup.product else None),
        brand_name=brand_name,
        batch_number=batch_number,
        barcode_or_qr=barcode_or_qr,
    )
    evidence.append(EvidenceItem(
        category="manufacturer_verification",
        source="Manufacturer Batch Adapter",
        detail=f"{mfg_result.manufacturer_name}: {mfg_result.details}",
        is_critical=not mfg_result.verified and mfg_result.status == "unverified",
    ))
    if mfg_result.status == "unverified" and batch_number:
        discrepancies.append(mfg_result.details)

    # --- 6. Determine Outcome based on Clinical & Regulatory Hierarchy ---
    outcome: AuthenticityOutcome
    outcome_label: str
    summary_message: str

    if is_recalled:
        outcome = "possible_recall"
        outcome_label = "Possible recall or safety alert"
        summary_message = (
            "This product or batch matches an official DRAP Rapid Alert or recall notification. "
            "Do not consume or dispense this medicine."
        )
    elif is_expired:
        outcome = "expired"
        outcome_label = "Expired"
        summary_message = (
            f"The medicine packaging indicates an expiry date ({expiry_date_text}) that is in the past. "
            "Expired medicines may lose potency or form toxic degradation products."
        )
    elif len(discrepancies) > 0 and (
        any(
            any(k in d.lower() for k in ("mismatch", "alert", "future", "deviates", "anomaly", "suspicious", "invalid", "visual"))
            for d in discrepancies
        )
        or len(altered_label_flags) > 0
        or len(visual_packaging_flags) > 0
    ):
        outcome = "potentially_suspicious"
        outcome_label = "Potentially suspicious"
        summary_message = (
            "Significant discrepancies or packaging abnormalities were detected when compared with "
            "DRAP registration records or manufacturer packaging standards."
        )
    elif reg_lookup.found and mfg_result.verified and mfg_result.is_live_service:
        outcome = "verified_authoritative"
        outcome_label = "Verified through an authoritative source"
        summary_message = (
            "Registration confirmed with DRAP and batch verified with the authorized manufacturer. "
            "Physical package authenticity still requires visual confirmation."
        )
    elif reg_lookup.found:
        outcome = "registered_unconfirmed"
        outcome_label = "Registered product found — package authenticity unconfirmed"
        summary_message = (
            f"An active DRAP registration was found for {reg_lookup.product.brand_name} (Reg #{reg_lookup.product.registration_no}), "
            "matching the visible details. However, physical packaging authenticity cannot be confirmed solely from a photograph."
        )
    else:
        outcome = "inconclusive"
        outcome_label = "Inconclusive — more information needed"
        summary_message = (
            "Available details could not be matched with authoritative DRAP records or the photograph lacked "
            "sufficient clarity. A licensed pharmacist should review the physical package."
        )

    # --- 7. Recommended Next Steps ---
    next_steps: list[str] = []
    if outcome == "possible_recall":
        next_steps.extend([
            "Do NOT consume or administer this medicine under any circumstances.",
            "Quarantine the medicine in a secure location away from other medications.",
            "Generate a DRAP complaint draft using the button below and report immediately to your local Drug Inspector.",
            "Return to the dispensing pharmacy with your receipt for formal regulatory escalation.",
        ])
    elif outcome == "expired":
        next_steps.extend([
            "Do not consume expired medicines; safely dispose according to provincial guidelines.",
            "Obtain a fresh, unexpired prescription or replacement from a licensed pharmacy.",
            "Verify storage conditions and dates whenever purchasing new medications.",
        ])
    elif outcome == "potentially_suspicious":
        next_steps.extend([
            "Do not take this medicine until it has been inspected by a licensed pharmacist.",
            "Keep the original packaging, blister packs, and sales receipt intact.",
            "Prepare a formal DRAP Suspicious Medicine Draft report using After Dr.",
            "Report the pharmacy or distributor to DRAP's Vigilance Cell (051-9107416).",
        ])
    elif outcome == "registered_unconfirmed":
        next_steps.extend([
            "Examine physical packaging for authentic security holograms, clean embossing, and intact tamper seals.",
            "Confirm the medicine was dispensed from a licensed and reputable retail pharmacy.",
            "If any unexpected physical appearance (odor, discoloration, broken seal) is noted, consult your pharmacist.",
        ])
    else:  # inconclusive
        next_steps.extend([
            "Take a sharper, well-lit photograph capturing the complete registration number and batch details.",
            "Check that the DRAP Registration Number (e.g. Reg. No. 012345) is clearly legible on the box.",
            "Present the packaging to a licensed pharmacist for manual in-person verification.",
        ])

    return AuthenticityAssessment(
        outcome=outcome,
        outcome_label=outcome_label,
        summary_message=summary_message,
        is_expired=is_expired,
        is_recalled=is_recalled,
        discrepancies=tuple(discrepancies),
        evidence=tuple(evidence),
        recommended_next_steps=tuple(next_steps),
        disclaimer=CORE_SAFETY_DISCLAIMER,
        source_links=tuple(source_links),
        assessed_at=datetime.now(timezone.utc).isoformat(),
    )
