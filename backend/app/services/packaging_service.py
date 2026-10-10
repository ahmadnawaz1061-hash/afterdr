"""Packaging workflows, patient-scoped evidence reuse, and stored-text reanalysis."""
from collections import defaultdict, deque
from contextlib import contextmanager
import hashlib
import json
import os
from threading import Lock
import time
from datetime import datetime, timezone

from sqlmodel import Session, select
from app.models import Verification
from app.services import gemini_service, packaging_online_service
from app.services.packaging_contracts import PackagingVision, PackagingFields, PackagingCorrections, PackagingAssessment, PackagingHistoryItem, ImageQuality, OnlineLookup
from app.services.packaging_assessment import assess_packaging, STATUS_LABELS, LIMITATIONS
from app.services.image_validation import prepare_package_image, ImageValidationError, ImageTooLargeError, MAX_PACKAGING_REQUEST_SIZE
from app.services.packaging_reference import REFERENCE_PATH

LEGACY_STATUS = {'likely_consistent': 'record_match', 'suspicious': 'inconsistent_information', 'unable_to_assess': 'unable_to_verify'}
ANALYSIS_VERSION = 'packaging-v4-readable-identity'
_guard = Lock()
_inflight = set()
_calls = defaultdict(deque)


class PackagingWorkflowError(RuntimeError):
    status_code = 400
    public_message = 'Packaging analysis could not be completed'


class PackagingNotFoundError(PackagingWorkflowError):
    status_code = 404
    public_message = 'Packaging check not found'


class PackagingRateLimitError(PackagingWorkflowError):
    status_code = 429
    public_message = 'Too many packaging analyses. Wait a minute before trying again.'
    retry_after = '60'


class PackagingSaveError(PackagingWorkflowError):
    status_code = 500
    public_message = 'The packaging assessment could not be saved'


@contextmanager
def patient_analysis_slot(patient_id):
    with _guard:
        if patient_id in _inflight:
            raise PackagingRateLimitError('An analysis for this account is already running')
        _inflight.add(patient_id)
    try:
        yield
    finally:
        with _guard:
            _inflight.discard(patient_id)


def _limit_calls(patient_id):
    try:
        limit = int(os.getenv('PACKAGING_REQUESTS_PER_MINUTE', '5'))
        if not 1 <= limit <= 30:
            raise ValueError
    except ValueError as exc:
        raise gemini_service.GeminiConfigurationError('Invalid PACKAGING_REQUESTS_PER_MINUTE') from exc
    now = time.monotonic()
    with _guard:
        # Expire inactive account buckets to bound in-memory rate-limit state.
        for owner in list(_calls):
            while _calls[owner] and _calls[owner][0] <= now - 60:
                _calls[owner].popleft()
            if not _calls[owner]:
                del _calls[owner]
        if len(_calls[patient_id]) >= limit:
            raise PackagingRateLimitError()
        _calls[patient_id].append(now)


def _record_data(row):
    try:
        details = json.loads(row.extracted_details_json)
        if not isinstance(details, dict):
            return {}
        return details
    except (TypeError, ValueError):
        return {}


def _records(session, patient_id, *, limit=100, offset=0):
    return session.exec(select(Verification).where(Verification.patient_id == patient_id).order_by(Verification.id.desc()).offset(offset).limit(limit)).all()


def get_packaging_check(session, patient_id, verification_id):
    row = session.get(Verification, verification_id)
    if row is None or row.patient_id != patient_id:
        raise PackagingNotFoundError()
    data = _record_data(row)
    if data.get('schema_version') == 2:
        try:
            return PackagingAssessment.model_validate_json(row.findings_json)
        except ValueError as exc:
            raise PackagingWorkflowError('Stored packaging assessment is unavailable') from exc
    # Legacy history is displayed as unassessed evidence, never elevated to a
    # new consistency verdict based on old fabricated/provider claims.
    fields = PackagingFields.model_validate({key: data.get(key) for key in PackagingFields.model_fields})
    return PackagingAssessment(verification_id=row.id, status='unable_to_assess', status_label=STATUS_LABELS['unable_to_assess'], risk_level='unknown', risk_score=None,
        summary='This check was created with the previous verification workflow. Upload packaging photos for the current analysis.', extracted=fields,
        signals=[], next_steps=['Upload clear photographs for a new packaging assessment.'], registration_state='not_visible' if not fields.registration_number else 'not_in_reference',
        source='legacy_record', limitations=LIMITATIONS, simulated=row.source == 'demo_dataset', assessed_at='', counterfeit_confirmed=False)


def list_packaging_checks(session, patient_id, limit=10, offset=0):
    items = []
    for row in _records(session, patient_id, limit=limit, offset=offset):
        result = get_packaging_check(session, patient_id, row.id)
        items.append(PackagingHistoryItem(verification_id=row.id, brand_name=result.extracted.brand_name, status=result.status,
            status_label=result.status_label, risk_level=result.risk_level, risk_score=result.risk_score, simulated=result.simulated, assessed_at=result.assessed_at or None))
    return items


def _save_assessment(session, patient_id, result, metadata):
    row = Verification(patient_id=patient_id, medicine_id=None, status=LEGACY_STATUS[result.status], source=result.source,
                       extracted_details_json=json.dumps(metadata), findings_json='{}')
    try:
        session.add(row)
        session.flush()
        result.verification_id = row.id
        row.findings_json = result.model_dump_json()
        session.commit()
        return result
    except Exception as exc:
        session.rollback()
        raise PackagingSaveError() from exc


def analyze_packaging(session, patient_id, images, corrections=None, trusted_reference=None):
    if not 1 <= len(images) <= 3:
        raise ImageValidationError('Upload a front photograph and at most two additional photos')
    if sum(map(len, images)) + len(trusted_reference or b'') > MAX_PACKAGING_REQUEST_SIZE:
        raise ImageTooLargeError('Total images exceed the 12 MB limit')
    with patient_analysis_slot(patient_id):
        prepared = [prepare_package_image(data, i + 1, ('front', 'back_or_side', 'close_up')[i]) for i, data in enumerate(images)]
        comparator = prepare_package_image(trusted_reference, len(images) + 1, 'user_supplied_reference') if trusted_reference else None
        quality = [ImageQuality(**photo.quality) for photo in prepared + ([comparator] if comparator else [])]
        simulated = gemini_service.using_mock_ai()
        scenario = os.getenv('PACKAGING_DEMO_SCENARIO', 'consistent') if simulated else None
        if simulated and scenario not in gemini_service.DEMO_PACKAGE_SCENARIOS:
            raise gemini_service.GeminiConfigurationError('Invalid PACKAGING_DEMO_SCENARIO')
        model = 'mock' if simulated else os.getenv('GEMINI_MODEL', '').strip()
        image_hash = hashlib.sha256(json.dumps([hashlib.sha256(data).hexdigest() for data in images + ([trusted_reference] if trusted_reference else [])]).encode()).hexdigest()
        reference_hash = hashlib.sha256(REFERENCE_PATH.read_bytes()).hexdigest() if REFERENCE_PATH.exists() else 'no_reference'
        fingerprint = hashlib.sha256(json.dumps([image_hash, model, scenario, simulated, ANALYSIS_VERSION, reference_hash]).encode()).hexdigest()
        updates = (corrections or PackagingCorrections()).model_dump(exclude_unset=True)
        existing_vision = None
        for row in _records(session, patient_id):
            saved = _record_data(row)
            if saved.get('fingerprint') != fingerprint:
                continue
            if saved.get('corrections', {}) == updates:
                previous = get_packaging_check(session, patient_id, row.id)
                if _lookup_is_current(previous.online_lookup, simulated):
                    return previous.model_copy(update={'cached': True})
            existing_vision = PackagingVision.model_validate(saved['vision'])
            break
        if existing_vision is not None:
            vision = existing_vision
        elif all(photo.quality['unusable'] for photo in prepared) and not simulated:
            vision = PackagingVision(image_quality='unreadable', quality_issues=['All target photos are unusable; no Gemini request was made.'])
        else:
            _limit_calls(patient_id)
            vision = gemini_service.analyze_package_images(prepared, trusted_reference=comparator)
        fields = vision.extracted.model_copy(update=updates)
        lookup = packaging_online_service.search_package_reference(fields) if not simulated else OnlineLookup(status='simulated', summary='Demo mode does not query the internet; no live product match is claimed.')
        result = assess_packaging(vision, quality, corrections, simulated=simulated, scenario=scenario, online_lookup=lookup)
        metadata = {'schema_version': 2, 'vision': vision.model_dump(), 'extracted': result.extracted.model_dump(), 'corrections': updates,
                    'quality': [q.model_dump() for q in quality], 'fingerprint': fingerprint, 'simulated': simulated, 'scenario': scenario, 'model': model}
        return _save_assessment(session, patient_id, result, metadata)


def reanalyze_packaging(session, patient_id, verification_id, corrections):
    row = session.get(Verification, verification_id)
    if row is None or row.patient_id != patient_id:
        raise PackagingNotFoundError()
    saved = _record_data(row)
    if saved.get('schema_version') != 2:
        raise PackagingWorkflowError('Legacy checks require new packaging photos')
    # A saved simulation cannot become real simply because the environment
    # changed. Its evidence origin is immutable through text correction.
    updates = dict(saved.get('corrections', {}))
    updates.update(corrections.model_dump(exclude_unset=True))
    merged = PackagingCorrections.model_validate(updates)
    vision = PackagingVision.model_validate(saved['vision'])
    quality = [ImageQuality.model_validate(q) for q in saved.get('quality', [])]
    result = assess_packaging(vision, quality, merged, simulated=saved['simulated'], scenario=saved.get('scenario'))
    original = get_packaging_check(session, patient_id, verification_id)
    search_fields = ('brand_name', 'manufacturer', 'active_ingredient', 'strength', 'dosage_form')
    if all(getattr(original.extracted, key) == getattr(result.extracted, key) for key in search_fields) and _lookup_is_current(original.online_lookup, saved['simulated']):
        result.online_lookup = original.online_lookup
    elif saved['simulated']:
        result.online_lookup = OnlineLookup(status='simulated', summary='Demo mode does not query the internet; no live product match is claimed.')
    else:
        result.online_lookup = packaging_online_service.search_package_reference(result.extracted)
    result = assess_packaging(vision, quality, merged, simulated=saved['simulated'], scenario=saved.get('scenario'), online_lookup=result.online_lookup)
    result.reanalysis_of = verification_id
    metadata = {**saved, 'extracted': result.extracted.model_dump(), 'corrections': updates}
    # Preserve report references and prior results with an immutable new revision.
    return _save_assessment(session, patient_id, result, metadata)


def _lookup_is_current(lookup, simulated):
    if simulated:
        return True
    if lookup.status in {'unavailable', 'not_searched'} or not lookup.searched_at:
        return False
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(lookup.searched_at)).total_seconds() < 900
    except (ValueError, TypeError):
        return False
