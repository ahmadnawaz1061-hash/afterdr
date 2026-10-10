"""Deterministic verdicts from separately attributed observations and references."""
from datetime import datetime, timezone
from app.services.packaging_contracts import PackagingAssessment, PackagingSignal, MatchedReference
from app.services.packaging_reference import find_brand_reference, normalize_name, normalize_manufacturer, manufacturer_matches, normalize_form, similarity
from app.services.alternative_service import normalize_matching_strength

STATUS_LABELS = {
    'likely_consistent': 'Looks consistent with an authentic product',
    'suspicious': 'Suspicious: possible knockoff or lookalike',
    'unable_to_assess': "Can't tell from these photos",
}
# Cap contributions by category to avoid double-counting model and reference
# descriptions of the same issue. Photo quality never adds counterfeit risk.
RISK_WEIGHTS = {
    'name_brand': {'low': 5, 'medium': 18, 'high': 40},
    'manufacturer': {'low': 5, 'medium': 18, 'high': 35},
    'registration': {'low': 5, 'medium': 20, 'high': 40},
    'ingredient_strength': {'low': 5, 'medium': 18, 'high': 35},
    'label_print': {'low': 3, 'medium': 8, 'high': 12},
    'packaging_design': {'low': 3, 'medium': 10, 'high': 15},
}
LIMITATIONS = [
    'Photographs cannot establish physical authenticity or confirm a counterfeit.',
    'The local catalog is a historical snapshot. The online price-index lookup documents product details, not physical authenticity or current registration validity; no recall lookup is performed.',
    'Packaging versions and printing can vary. A pharmacist or manufacturer should review concerning findings.',
]


def assess_packaging(vision, quality, corrections=None, *, simulated=False, scenario=None, references=None, online_lookup=None):
    fields = vision.extracted.model_copy(deep=True)
    signals = []
    if corrections is not None:
        updates = corrections.model_dump(exclude_unset=True)
        fields = fields.model_copy(update=updates)
        for field, value in updates.items():
            signals.append(PackagingSignal(category='registration' if field == 'registration_number' else 'manufacturer' if field == 'manufacturer' else 'name_brand' if field == 'brand_name' else 'ingredient_strength', severity='neutral', title='User-corrected ' + field.replace('_', ' '), detail=f'Assessment uses the supplied correction: {value or "not visible"}. Original image observations are retained separately.', origin='user_correction'))
    for observation in vision.signals:
        # Registration validity always comes from a trusted comparison. Vision
        # observations alone cannot assert official invalidity or contribute risk.
        if observation.category == 'registration':
            continue
        if corrections and observation.category == 'name_brand' and 'brand_name' in corrections.model_fields_set:
            severity = 'neutral'
        else:
            severity = observation.severity
        signals.append(PackagingSignal(**observation.model_dump(exclude={'severity'}), severity=severity,
                                       origin='simulated_demo' if simulated else 'vision_observation', simulated=simulated))
    for photo in quality:
        for issue in photo.issues:
            signals.append(PackagingSignal(category='image_quality', severity='neutral', title=f'Photo {photo.image_index}: quality guidance', detail=issue, origin='local_image_quality', image_index=photo.image_index))
    for issue in vision.quality_issues:
        signals.append(PackagingSignal(category='image_quality', severity='neutral', title='Label readability', detail=issue, origin='simulated_demo' if simulated else 'vision_observation', simulated=simulated))

    reference, kind, ratio, reliable_product = find_brand_reference(fields, references)
    # Unidentified names/manufacturers cannot acquire a serious identity warning
    # solely from a model's unfamiliarity. Corroborated references raise severity.
    if not reference:
        for signal in signals:
            if signal.category in {'name_brand', 'manufacturer'} and signal.severity == 'high':
                signal.severity = 'medium'
    matched = None
    manufacturer_match = False
    if reference:
        manufacturer_match = bool(fields.manufacturer and reference.get('manufacturer') and manufacturer_matches(fields.manufacturer, reference['manufacturer']))
        near_support = manufacturer_match and any(s.category == 'name_brand' and s.severity in {'medium', 'high'} and s.origin in {'vision_observation', 'simulated_demo'} for s in signals)
        matched = MatchedReference(
            brand_name=reference['brand_name'], active_ingredient=reference.get('active_ingredient'),
            strength=reference.get('strength'), dosage_form=reference.get('dosage_form'),
            manufacturer=reference.get('manufacturer'), registration_no=reference.get('registration_no'),
            data_source=reference['data_source'], source_url=reference.get('source_url'),
            last_verified_at=reference.get('last_verified_at'), match_kind=kind, similarity=ratio,
            comparison_status='Possible similar name; product identity requires review' if kind == 'lookalike' else 'Product name matches a sourced snapshot; physical authenticity unconfirmed',
            notes=reference.get('notes') or 'Available reference information is incomplete.',
        )
        if kind == 'lookalike':
            signals.append(PackagingSignal(category='name_brand', severity='high' if near_support and ratio >= .85 else 'neutral', title='Similar product name needs review', detail=f'Visible name "{fields.brand_name}" resembles "{reference["brand_name"]}" ({round(ratio * 100)}% name similarity). Similarity alone does not identify this product or establish a knockoff.', origin='reference_catalog', evidence=f'{fields.brand_name} / {reference["brand_name"]}', reference_url=reference.get('source_url')))
        else:
            signals.append(PackagingSignal(category='name_brand', severity='positive', title='Product name matches the reference', detail='The reviewed name matches a sourced product snapshot.', origin='reference_catalog', reference_url=reference.get('source_url')))
        if kind in {'exact', 'alias'} and fields.manufacturer and reference.get('manufacturer'):
            close = similarity(normalize_manufacturer(fields.manufacturer), normalize_manufacturer(reference['manufacturer']))
            signals.append(PackagingSignal(category='manufacturer', severity='positive' if manufacturer_match else 'high' if close < .65 and reliable_product else 'neutral', title='Manufacturer matches the reference' if manufacturer_match else 'Manufacturer differs from the available reference', detail=f'Visible: {fields.manufacturer}. Snapshot: {reference["manufacturer"]}. Company names/ownership can change; confirm with the manufacturer.', origin='reference_catalog', reference_url=reference.get('source_url')))
        if reliable_product:
            for field in ('active_ingredient', 'strength', 'dosage_form'):
                visible, expected = getattr(fields, field), reference.get(field)
                if not visible or not expected or expected.casefold() == 'unknown':
                    continue
                if field == 'strength':
                    left, right = normalize_matching_strength(visible), normalize_matching_strength(expected)
                    consistent = left == right
                    supported = left is not None and right is not None and len(left.split('+')) == len(right.split('+'))
                elif field == 'dosage_form':
                    consistent = normalize_form(visible) in normalize_form(expected)
                    supported = True
                else:
                    consistent = normalize_name(visible) == normalize_name(expected)
                    supported = True
                signals.append(PackagingSignal(category='ingredient_strength', severity='positive' if consistent else 'medium' if supported else 'neutral', title=field.replace('_', ' ').capitalize() + (' matches' if consistent else ' needs review'), detail=f'Visible: {visible}. Reference: {expected}. Unsupported formulations and salt synonyms require human review.', origin='reference_catalog', reference_url=reference.get('source_url')))
    else:
        signals.append(PackagingSignal(category='name_brand', severity='neutral', title='No reference match available', detail='This product could not be identified in the limited local catalog. Absence is not a warning sign.', origin='reference_catalog'))

    if not fields.registration_number:
        state = 'not_visible'
        reg_detail = 'No readable registration number was supplied.'
        reg_origin = 'user_correction' if corrections and 'registration_number' in corrections.model_fields_set else 'simulated_demo' if simulated else 'vision_observation'
        reg_severity = 'neutral'
    elif not reliable_product or not reference or not reference.get('registration_no'):
        state, reg_detail, reg_origin, reg_severity = 'not_in_reference', 'The visible number cannot be checked against an unambiguous sourced product reference.', 'reference_catalog', 'neutral'
    else:
        same = normalize_name(fields.registration_number) == normalize_name(reference['registration_no'])
        state = 'matched_reference' if same else 'mismatch'
        reg_detail = f'Visible: {fields.registration_number}. Available snapshot: {reference["registration_no"]}. This compares catalog values, not current official validity.'
        reg_origin, reg_severity = 'reference_catalog', 'positive' if same else 'high'
    signals.append(PackagingSignal(category='registration', severity=reg_severity, title={'matched_reference': 'Registration matches the snapshot', 'mismatch': 'Registration differs from the snapshot', 'not_visible': 'Registration not visible', 'not_in_reference': 'Registration could not be checked'}[state], detail=reg_detail, origin=reg_origin, registration_state=state, reference_url=reference.get('source_url') if reference else None))
    if simulated and scenario == 'registration_mismatch_demo':
        # Keep the visible/extracted number unchanged. This illustrates a finding
        # without inventing a regulatory number or changing the reference catalog.
        state = 'simulated_mismatch'
        signals.append(PackagingSignal(category='registration', severity='high', title='Simulated registration mismatch', detail='Demonstration-only conflict illustrating the risk workflow. The extracted registration is unchanged; this is not an actual DRAP determination.', origin='simulated_demo', registration_state=state, simulated=True))

    contributions = {}
    for signal in signals:
        amount = RISK_WEIGHTS.get(signal.category, {}).get(signal.severity, 0)
        contributions[signal.category] = max(contributions.get(signal.category, 0), amount)
    score = min(100, sum(contributions.values()))
    readable_identity = bool(fields.brand_name and (
        (fields.manufacturer and (fields.active_ingredient or fields.strength)) or
        (fields.active_ingredient and fields.strength)))
    # Global quality hints are not OCR failures: a readable side can rescue a
    # blurred front, and white backgrounds must not erase extracted evidence.
    target_quality = [q for q in quality if q.role != 'user_supplied_reference']
    poor = (vision.image_quality == 'unreadable' or
            (vision.image_quality == 'poor' and (not readable_identity or score > 0)) or
            bool(target_quality and all(q.unusable for q in target_quality) and not simulated))
    online_match = bool(online_lookup and online_lookup.status == 'matched' and online_lookup.product and online_lookup.sources)
    positives = {s.category for s in signals if s.severity == 'positive' and s.origin in {'vision_observation', 'simulated_demo'}}
    serious = any(s.severity == 'high' and s.category in {'name_brand', 'manufacturer', 'registration', 'ingredient_strength'} for s in signals)
    if poor or not fields.brand_name:
        status, score = 'unable_to_assess', None
        summary = ('Some medicine details were read, but the product name is missing. Add a clear view of the brand or correct the brand field below.'
                   if not fields.brand_name and any((fields.active_ingredient, fields.manufacturer, fields.strength))
                   else 'The label is not readable enough for a meaningful assessment. Add a focused front or side photo with the product details visible.')
    elif serious or score >= 35:
        status = 'suspicious'
        summary = 'The available evidence contains discrepancies that need professional inspection before relying on this package.'
    elif score == 0 and readable_identity and ((reference and kind in {'exact', 'alias'} and manufacturer_match) or online_match):
        status = 'likely_consistent'
        summary = 'The readable product identity matches documented product details. No warning signs were detected in the available evidence. This does not authenticate the physical package.'
    elif reference and kind in {'exact', 'alias'} and manufacturer_match and vision.image_quality == 'good' and len(positives) >= 2 and score == 0:
        status = 'likely_consistent'
        summary = 'The readable product details and available observations are consistent with the sourced reference. No major warning signs were detected in this evidence.'
    else:
        status = 'unable_to_assess'
        if not reference and not online_match:
            summary = 'The limited catalog does not identify this medicine. The photographs alone provide insufficient evidence for a consistency assessment.'
        else:
            summary = 'Some information is missing, uncertain or conflicting. Review the extracted text or take additional photos before drawing conclusions.'
        score = None
    risk = 'unknown' if score is None else 'high' if score >= 60 else 'medium' if score >= 20 else 'low'
    steps = ['Check the packaging with a pharmacist or the manufacturer.', 'Keep the packaging and purchase receipt for any follow-up.'] if status == 'suspicious' else ['Retake clear photos in even light, with no glare and the full label in view.', 'Review and correct any misread medicine details.'] if status == 'unable_to_assess' else ['Confirm any remaining concerns with a pharmacist or manufacturer.', 'Use the official DRAP website for further product enquiries.']
    severity_order = {'high': 0, 'medium': 1, 'low': 2, 'neutral': 3, 'positive': 4}
    signals.sort(key=lambda s: severity_order[s.severity])
    return PackagingAssessment(status=status, status_label=STATUS_LABELS[status], risk_level=risk, risk_score=score,
        summary=summary, extracted=fields, signals=signals, next_steps=steps, matched_reference=matched,
        registration_state=state, source='simulated_demo' if simulated else 'Gemini vision + local image checks + offline product references',
        limitations=LIMITATIONS, simulated=simulated, image_quality=quality,
        **({'online_lookup': online_lookup} if online_lookup is not None else {}),
        assessed_at=datetime.now(timezone.utc).isoformat())
