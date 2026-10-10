from io import BytesIO
import json
from types import SimpleNamespace
import asyncio
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.main import app
from app.database import get_session
from app.models import Patient, Verification
from app.schemas import ReportCreateRequest
from app.services import gemini_service, packaging_service, packaging_online_service
from app.services.packaging_contracts import PackagingFields, PackagingCorrections, PackagingVision, VisualSignal, ImageQuality
from app.services.packaging_assessment import assess_packaging
from app.services.packaging_reference import similarity, find_brand_reference, load_brand_references
from app.services.image_validation import prepare_package_image, MAX_IMAGE_SIZE, ImageDimensionsError
from app.services.report_service import create_report_draft, generate_report_pdf


def photo(format='PNG', size=(700, 500)):
    image = Image.new('RGB', size, 'white')
    draw = ImageDraw.Draw(image)
    for x in range(30, size[0] - 30, 30):
        draw.rectangle((x, 30, x + 12, size[1] - 30), fill='#315352')
    out = BytesIO(); image.save(out, format=format)
    return out.getvalue()


@pytest.fixture
def packaging_db(monkeypatch):
    from app.services.packaging_contracts import OnlineLookup
    monkeypatch.setattr(packaging_online_service, 'search_package_reference', lambda fields: OnlineLookup(status='not_found', summary='No internet result in this test fixture.'))
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Patient(id=1, demo_name='Test patient'), Patient(id=2, demo_name='Other patient')]); session.commit()
    def override():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = override
    packaging_service._calls.clear(); packaging_service._inflight.clear()
    monkeypatch.setenv('PACKAGING_DEMO_SCENARIO', 'consistent')
    with TestClient(app) as client:
        yield client, engine
    app.dependency_overrides.pop(get_session, None)
    engine.dispose()


def upload(client, count=1, **kwargs):
    return client.post('/api/verifications/analyze', files=[('images', ('pack.jpg', photo(), 'image/jpeg')) for _ in range(count)], **kwargs)


@pytest.mark.parametrize('count', [1, 2, 3])
def test_image_count_and_content_validation(packaging_db, count):
    client, engine = packaging_db
    response = upload(client, count)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['verification_id'] > 0 and data['counterfeit_confirmed'] is False
    assert len(data['image_quality']) == count
    assert data['simulated'] is True
    with Session(engine) as session:
        row = session.get(Verification, data['verification_id'])
        saved = json.loads(row.extracted_details_json)
        assert saved['schema_version'] == 2
        assert 'images' not in saved and 'bytes' not in row.extracted_details_json


@pytest.mark.parametrize('scenario,status', [('consistent', 'likely_consistent'), ('suspicious_lookalike', 'suspicious'), ('registration_mismatch_demo', 'suspicious'), ('unclear_image', 'unable_to_assess')])
def test_all_deterministic_scenarios(packaging_db, monkeypatch, scenario, status):
    monkeypatch.setenv('PACKAGING_DEMO_SCENARIO', scenario)
    response = upload(packaging_db[0]).json()
    assert response['status'] == status and response['counterfeit_confirmed'] is False
    assert response['simulated'] is True
    if scenario == 'registration_mismatch_demo':
        assert response['extracted']['registration_number'] == '101138'
        assert response['registration_state'] == 'simulated_mismatch'
        assert any(s['origin'] == 'simulated_demo' and s['registration_state'] == 'simulated_mismatch' for s in response['signals'])


@pytest.mark.parametrize('files,expected', [([], 400), ([('images', ('bad.png', b'not-an-image', 'image/png'))], 400), ([('images', ('large.png', b'x' * (MAX_IMAGE_SIZE + 1), 'image/png'))], 413), ([('images', ('a.png', photo(), 'image/png'))] * 4, 400), ([('images', ('a.gif', photo('GIF'), 'image/gif'))], 400)])
def test_invalid_uploads(packaging_db, files, expected):
    response = packaging_db[0].post('/api/verifications/analyze', files=files)
    assert response.status_code == expected


def test_total_multipart_request_limit(packaging_db):
    response = packaging_db[0].post('/api/verifications/analyze', content=b'x' * (12 * 1024 * 1024 + 1), headers={'content-type': 'multipart/form-data; boundary=test'})
    assert response.status_code == 413


def test_optional_reference_and_legacy_file_field(packaging_db):
    client, _ = packaging_db
    response = client.post('/api/verifications/analyze', files={'file': ('front.png', photo(), 'image/png'), 'trusted_reference': ('reference.png', photo(), 'image/png')})
    assert response.status_code == 201
    assert response.json()['image_quality'][-1]['role'] == 'user_supplied_reference'


def test_real_unusable_photo_makes_no_gemini_call(packaging_db, monkeypatch):
    monkeypatch.setenv('USE_MOCK_AI', 'false')
    monkeypatch.setattr(gemini_service, 'analyze_package_images', lambda *a, **kw: pytest.fail('Unusable image must not consume quota'))
    response = packaging_db[0].post('/api/verifications/analyze', files={'images': ('tiny.png', photo(size=(20, 20)), 'image/png')})
    assert response.status_code == 201
    assert response.json()['status'] == 'unable_to_assess'
    assert response.json()['risk_score'] is None and not response.json()['simulated']


def consistent_vision():
    return gemini_service._mock_package_analysis('consistent')


@pytest.mark.parametrize('quality', ['good', 'fair', 'poor'])
def test_readable_identity_does_not_require_positive_visual_signals(quality):
    vision = consistent_vision()
    vision.signals = []
    vision.image_quality = quality
    vision.extracted.registration_number = None
    result = assess_packaging(vision, [])
    assert result.status == 'likely_consistent'
    assert result.risk_score == 0
    assert not result.counterfeit_confirmed


def test_online_source_can_corroborate_product_outside_local_catalog():
    from app.services.packaging_contracts import OnlineLookup, OnlineSource
    fields = PackagingFields(brand_name='Documented brand', manufacturer='Documented company', active_ingredient='Example ingredient')
    vision = PackagingVision(extracted=fields, image_quality='fair')
    lookup = OnlineLookup(status='matched', summary='Sourced match', product=fields, sources=[OnlineSource(title='DRAP', url='https://e.dra.gov.pk/public/price')])
    assert assess_packaging(vision, [], references=[], online_lookup=lookup).status == 'likely_consistent'
    assert assess_packaging(vision, [], references=[]).status == 'unable_to_assess'
    vision.image_quality = 'unreadable'
    assert assess_packaging(vision, [], references=[], online_lookup=lookup).status == 'unable_to_assess'


def test_online_match_does_not_require_manufacturer_on_front():
    from app.services.packaging_contracts import OnlineLookup, OnlineSource
    fields = PackagingFields(brand_name='Documented brand', active_ingredient='Example ingredient', strength='200 mg')
    vision = PackagingVision(extracted=fields, image_quality='fair')
    lookup = OnlineLookup(status='matched', summary='Unambiguous sourced match', product=fields, sources=[OnlineSource(title='DRAP', url='https://e.dra.gov.pk/public/price')])
    assert assess_packaging(vision, [], references=[], online_lookup=lookup).status == 'likely_consistent'


def test_readable_side_rescues_unusable_front(packaging_db, monkeypatch):
    monkeypatch.setenv('USE_MOCK_AI', 'false')
    calls = []
    def analyze(images, **kwargs):
        calls.append(len(images))
        return consistent_vision()
    monkeypatch.setattr(gemini_service, 'analyze_package_images', analyze)
    response = packaging_db[0].post('/api/verifications/analyze', files=[
        ('images', ('tiny.png', photo(size=(20, 20)), 'image/png')),
        ('images', ('side.png', photo(), 'image/png'))])
    assert response.status_code == 201
    assert calls == [2]
    assert response.json()['status'] == 'likely_consistent'


def test_printed_manufacturer_abbreviation_matches_documented_company():
    from app.services.packaging_reference import manufacturer_matches
    assert manufacturer_matches('Abbott', 'Abbott Laboratories (Pakistan) Limited')
    assert not manufacturer_matches('Abbott', 'Different laboratories')


def test_plural_dosage_form_does_not_create_a_false_conflict():
    vision = consistent_vision()
    vision.extracted.dosage_form = 'Tablets'
    result = assess_packaging(vision, [])
    assert result.status == 'likely_consistent'
    assert result.risk_score == 0


def test_unknown_brand_absence_not_suspicious():
    vision = PackagingVision(extracted=PackagingFields(brand_name='Unknown product', registration_number='123456'), image_quality='good')
    result = assess_packaging(vision, [])
    assert result.status == 'unable_to_assess' and result.risk_score is None
    assert result.registration_state == 'not_in_reference'
    assert not any(s.severity in {'medium', 'high'} for s in result.signals)


@pytest.mark.parametrize('reg,state,status', [('101138', 'matched_reference', 'likely_consistent'), ('999999', 'mismatch', 'suspicious'), (None, 'not_visible', 'likely_consistent')])
def test_real_registration_comparisons(reg, state, status):
    vision = consistent_vision(); vision.extracted.registration_number = reg
    result = assess_packaging(vision, [], simulated=False)
    assert result.registration_state == state and result.status == status
    assert all(not s.simulated and s.origin != 'simulated_demo' for s in result.signals)
    assert result.counterfeit_confirmed is False


def test_manufacturer_mismatch_and_score_ordering():
    vision = consistent_vision()
    good = assess_packaging(vision, [])
    vision.extracted.manufacturer = 'Completely Different Industrial Supplier'
    bad = assess_packaging(vision, [])
    assert bad.status == 'suspicious' and bad.risk_score > good.risk_score
    vision.extracted.registration_number = '999999'
    worse = assess_packaging(vision, [])
    assert worse.risk_score > bad.risk_score


@pytest.mark.parametrize('left,right', [('Panadol', 'Panadoll'), ('Augmentin', 'Augmentln'), ('Sooper', 'Snooper')])
def test_algorithmic_near_misses_are_not_automatic_authenticity_claims(left, right):
    assert .7 < similarity(left, right) < 1
    record = {'brand_name': left, 'manufacturer': 'Example company', 'data_source': 'test_fixture', 'registration_no': None}
    vision = PackagingVision(extracted=PackagingFields(brand_name=right), image_quality='good')
    result = assess_packaging(vision, [], references=[record])
    assert result.status == 'unable_to_assess'
    assert result.matched_reference.match_kind == 'lookalike'
    assert not any(s.severity == 'high' for s in result.signals)


def test_csv_loader_handles_optional_values_and_excludes_synthetic(tmp_path):
    path = tmp_path / 'brands.csv'
    path.write_text('brand_name,aliases,data_source,source_url\nExample,Alias,drap_pk,https://www.dra.gov.pk/\nSynthetic,,simulated_demo,https://www.dra.gov.pk/\n', encoding='utf-8')
    records = load_brand_references(path)
    assert len(records) == 1
    row, kind, _, _ = find_brand_reference(PackagingFields(brand_name='Alias'), records)
    assert kind == 'alias' and row['brand_name'] == 'Example'


def test_reuse_images_and_reanalysis_preserve_original_evidence(packaging_db, monkeypatch):
    client, engine = packaging_db
    first = upload(client).json()
    monkeypatch.setattr(gemini_service, 'analyze_package_images', lambda *a, **kw: pytest.fail('Must reuse stored observations'))
    second = upload(client).json()
    assert second['verification_id'] == first['verification_id'] and second['cached']
    corrected = client.post(f"/api/verifications/{first['verification_id']}/reanalyze", json={'registration_number': '999999'}).json()
    assert corrected['status'] == 'suspicious' and corrected['reanalysis_of'] == first['verification_id']
    assert corrected['verification_id'] != first['verification_id']
    assert corrected['simulated']
    assert client.get(f"/api/verifications/{first['verification_id']}").json()['extracted']['registration_number'] == '101138'
    assert len(client.get('/api/verifications').json()) == 2


def test_patient_isolation(packaging_db):
    client, engine = packaging_db
    with Session(engine) as session:
        row = Verification(patient_id=2, extracted_details_json='{}', findings_json='[]', status='unable_to_verify', source='test')
        session.add(row); session.commit(); row_id = row.id
    assert client.get(f'/api/verifications/{row_id}').status_code == 404
    assert client.post(f'/api/verifications/{row_id}/reanalyze', json={}).status_code == 404
    assert client.get('/api/verifications').json() == []


def test_no_demo_injection_in_real_mode(packaging_db, monkeypatch):
    monkeypatch.setenv('USE_MOCK_AI', 'false'); monkeypatch.setenv('PACKAGING_DEMO_SCENARIO', 'registration_mismatch_demo')
    monkeypatch.setattr(gemini_service, 'analyze_package_images', lambda *a, **kw: consistent_vision())
    result = upload(packaging_db[0]).json()
    assert result['registration_state'] == 'matched_reference'
    assert not result['simulated'] and all(not s['simulated'] for s in result['signals'])


def test_model_registration_claim_is_ignored():
    vision = consistent_vision()
    vision.signals.append(VisualSignal(category='registration', severity='high', title='Unsupported registry claim', detail='Model cannot check a registry', evidence='No reference'))
    result = assess_packaging(vision, [])
    assert result.status == 'likely_consistent'
    assert not any(s.title == 'Unsupported registry claim' for s in result.signals)


def test_poor_images_override_a_serious_warning():
    vision = consistent_vision(); vision.image_quality = 'poor'; vision.extracted.registration_number = '999999'
    result = assess_packaging(vision, [])
    assert result.status == 'unable_to_assess' and result.risk_score is None


def test_printing_alone_does_not_mark_product_suspicious():
    vision = consistent_vision()
    vision.signals.append(VisualSignal(category='label_print', severity='high', title='Uneven print', detail='Printing varies', evidence='Visible uneven spacing'))
    result = assess_packaging(vision, [])
    assert result.status == 'unable_to_assess'


def test_new_report_content_and_excluded_fields(packaging_db):
    client, engine = packaging_db
    result = upload(client).json()
    with Session(engine) as session:
        report = create_report_draft(session, ReportCreateRequest(verification_id=result['verification_id'], pharmacy_name='Test pharmacy', description='Review packaging evidence'))
        pdf = generate_report_pdf(session, report.id)
    assert b'DRAFT \\227 NOT SUBMITTED' in pdf
    assert b'Verification identifier' in pdf and b'Risk level' in pdf and b'Assessment status' in pdf
    assert b'Simulated demo data' in pdf and b'Recommended next steps' in pdf
    assert b'Batch number' not in pdf and b'Expiry date' not in pdf and b'barcode' not in pdf


@pytest.mark.parametrize('error,status', [(gemini_service.GeminiTimeoutError, 502), (gemini_service.GeminiAccessError, 502), (gemini_service.GeminiQuotaError, 429), (gemini_service.GeminiConfigurationError, 503), (gemini_service.GeminiModelError, 503), (gemini_service.GeminiResponseError, 502)])
def test_provider_errors_are_safe(packaging_db, monkeypatch, error, status):
    monkeypatch.setenv('USE_MOCK_AI', 'false')
    def fail(*a, **kw):
        raise error('private/internal error')
    monkeypatch.setattr(gemini_service, 'analyze_package_images', fail)
    response = upload(packaging_db[0])
    assert response.status_code == status
    assert 'private/internal' not in response.text
    if status == 429: assert response.headers['retry-after'] == '60'


def test_local_quota_reuses_cached_images_without_new_call(packaging_db, monkeypatch):
    monkeypatch.setenv('PACKAGING_REQUESTS_PER_MINUTE', '1')
    first = upload(packaging_db[0]); assert first.status_code == 201
    second = upload(packaging_db[0]); assert second.status_code == 201 and second.json()['cached']
    different = packaging_db[0].post('/api/verifications/analyze', files={'images': ('other.png', photo(size=(710, 510)), 'image/png')})
    assert different.status_code == 429


def test_one_gemini_request_for_all_images(monkeypatch):
    monkeypatch.setenv('USE_MOCK_AI', 'false')
    calls = []
    fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: (calls.append(kw) or SimpleNamespace(parsed=consistent_vision().model_dump()))), close=lambda: None)
    monkeypatch.setattr(gemini_service, '_client_and_model', lambda **kw: (fake, 'configured-image-model'))
    images = [prepare_package_image(photo(), i + 1, 'front' if i == 0 else 'back') for i in range(3)]
    result = gemini_service.analyze_package_images(images, trusted_reference=images[0])
    assert result.extracted.brand_name == 'Panadol' and len(calls) == 1
    assert len([p for p in calls[0]['contents'] if not isinstance(p, str)]) == 4
    assert calls[0]['config'].response_schema is not None
    assert 'additional_properties' not in json.dumps(calls[0]['config'].model_dump(exclude_none=True))


def test_strict_gemini_output_cannot_set_a_verdict(monkeypatch):
    monkeypatch.setenv('USE_MOCK_AI', 'false')
    fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(parsed={'status': 'likely_consistent'})), close=lambda: None)
    monkeypatch.setattr(gemini_service, '_client_and_model', lambda **kw: (fake, 'configured-model'))
    with pytest.raises(gemini_service.GeminiResponseError):
        gemini_service.analyze_package_images([prepare_package_image(photo(), 1, 'front')])


def test_streamed_request_limit_applies_without_content_length():
    from app.services.packaging_upload_limit import PackagingUploadLimitMiddleware
    from app.services.image_validation import MAX_PACKAGING_REQUEST_SIZE
    messages = iter([
        {'type': 'http.request', 'body': b'x' * (7 * 1024 * 1024), 'more_body': True},
        {'type': 'http.request', 'body': b'x' * (MAX_PACKAGING_REQUEST_SIZE - 7 * 1024 * 1024 + 1), 'more_body': False},
    ])
    sent = []
    async def receive():
        return next(messages)
    async def send(message):
        sent.append(message)
    async def downstream(*args):
        pytest.fail('Oversized streamed payload must not reach multipart parsing')
    asyncio.run(PackagingUploadLimitMiddleware(downstream)({'type': 'http', 'path': '/api/verifications/analyze', 'headers': []}, receive, send))
    assert sent[0]['status'] == 413


def test_preparation_corrects_orientation_and_strips_metadata():
    image = Image.open(BytesIO(photo(size=(3000, 1000))))
    exif = image.getexif(); exif[274] = 6; exif[270] = 'private camera metadata'
    out = BytesIO(); image.save(out, 'JPEG', exif=exif)
    prepared = prepare_package_image(out.getvalue(), 1, 'front')
    assert (prepared.quality['width'], prepared.quality['height']) == (1000, 3000)
    with Image.open(BytesIO(prepared.data)) as result:
        assert result.height == 2200 and result.width < result.height
        assert not result.getexif()
    assert b'private camera metadata' not in prepared.data


def test_new_preparation_enforces_dimension_limits():
    with pytest.raises(ImageDimensionsError):
        prepare_package_image(photo(size=(6001, 100)), 1, 'front')


def test_new_endpoints_require_authentication(packaging_db):
    from app.services.auth_service import get_current_user
    override = app.dependency_overrides.pop(get_current_user)
    try:
        client = packaging_db[0]
        assert upload(client).status_code == 401
        assert client.get('/api/verifications').status_code == 401
        assert client.get('/api/verifications/1').status_code == 401
        assert client.post('/api/verifications/1/reanalyze', json={}).status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = override


def test_duplicate_findings_do_not_inflate_risk():
    vision = consistent_vision()
    observation = VisualSignal(category='label_print', severity='high', title='Uneven print', detail='The same underlying issue', evidence='Same print defect')
    vision.signals.append(observation)
    initial = assess_packaging(vision, [])
    vision.signals.extend([observation] * 5)
    repeated = assess_packaging(vision, [])
    assert repeated.status == initial.status
    # Inconclusive scores remain null; test a scored result with the same defect.
    vision.extracted.registration_number = '999999'
    assert assess_packaging(vision, []).risk_score == 52


def test_simulated_evidence_stays_simulated_after_config_change(packaging_db, monkeypatch):
    client = packaging_db[0]
    initial = upload(client).json()
    monkeypatch.setenv('USE_MOCK_AI', 'false')
    monkeypatch.setattr(gemini_service, 'analyze_package_images', lambda *args, **kw: pytest.fail('Text reanalysis must not call Gemini'))
    revised = client.post(f"/api/verifications/{initial['verification_id']}/reanalyze", json={'pack_type': 'Carton'}).json()
    assert revised['simulated'] and revised['source'] == 'simulated_demo'


def test_corrections_cannot_inject_a_verdict(packaging_db):
    initial = upload(packaging_db[0]).json()
    response = packaging_db[0].post(f"/api/verifications/{initial['verification_id']}/reanalyze", json={'status': 'likely_consistent'})
    assert response.status_code == 422


def test_online_failure_does_not_discard_real_analysis_and_can_retry_without_images(packaging_db, monkeypatch):
    from app.services.packaging_contracts import OnlineLookup
    monkeypatch.setenv('USE_MOCK_AI', 'false')
    calls = []
    def vision(*args, **kwargs):
        calls.append(True)
        return consistent_vision()
    monkeypatch.setattr(gemini_service, 'analyze_package_images', vision)
    monkeypatch.setattr(packaging_online_service, 'search_package_reference', lambda fields: OnlineLookup(status='unavailable', summary='Source offline'))
    first = upload(packaging_db[0]).json()
    assert first['status'] == 'likely_consistent' and first['online_lookup']['status'] == 'unavailable'
    monkeypatch.setattr(packaging_online_service, 'search_package_reference', lambda fields: OnlineLookup(status='matched', summary='Source recovered', searched_at='2026-10-10T00:00:00+00:00'))
    second = upload(packaging_db[0]).json()
    assert second['online_lookup']['status'] == 'matched' and len(calls) == 1


def test_simulated_analysis_never_makes_an_internet_request(packaging_db, monkeypatch):
    monkeypatch.setattr(packaging_online_service, 'search_package_reference', lambda fields: pytest.fail('Simulated checks must not query live sources'))
    result = upload(packaging_db[0]).json()
    assert result['online_lookup']['status'] == 'simulated'
