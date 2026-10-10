"""Live source lookup uses bounded public HTTP and keeps identity separate."""
import httpx
import pytest
from google.genai import errors
from app.services import packaging_online_service as online, gemini_service
from app.services.packaging_contracts import PackagingFields


def row(brand='BRUFEN TABLETS 200MG', manufacturer='Abbott Laboratories (Pakistan) Limited', composition='Each tablet contains: Ibuprofen 200mg.'):
    return f'<tr><td><div class="text-sm font-medium text-gray-900">{brand}</div><div class="max-w-[200px] text-sm">{composition}</div></td><td>000072</td><td><div class="text-sm text-gray-900">{manufacturer}</div></td><td>Essential</td><td>10X10S</td><td>Price</td><td>Date</td></tr>'


def fields():
    return PackagingFields(brand_name='Brufen', manufacturer='Abbott Laboratories (Pakistan) Limited', active_ingredient='Ibuprofen', strength='200 mg', dosage_form='tablet')


@pytest.fixture
def public_source(monkeypatch):
    online._cache.clear()
    original = httpx.Client
    state = {'html': '<table>'+row()+'</table>', 'requests': [], 'page': '<input name="_token" value="test-token">', 'fail': False}
    def handle(request):
        state['requests'].append(request)
        if state['fail']: raise httpx.ConnectError('private internal error',request=request)
        return httpx.Response(200, text=state['page'] if request.method=='GET' else state['html'])
    monkeypatch.setattr(online.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    yield state
    online._cache.clear()


def test_live_documented_identity_and_cached_lookup(public_source):
    supplied=fields(); supplied.registration_number='private-number'
    result=online.search_package_reference(supplied)
    assert result.status=='matched' and result.product.brand_name=='BRUFEN TABLETS 200MG'
    assert result.product.strength=='200 mg' and result.product.active_ingredient=='Ibuprofen'
    assert result.product.registration_number is None
    assert result.sources[0].url==online.BASE_URL and result.searched_at
    assert len(public_source['requests'])==2
    assert all('private-number' not in str(request.content) for request in public_source['requests'])
    assert online.search_package_reference(supplied).status=='matched'
    assert len(public_source['requests'])==2


def test_missing_brand_never_makes_a_request(public_source):
    assert online.search_package_reference(PackagingFields()).status=='not_searched'
    assert not public_source['requests']


@pytest.mark.parametrize('updates',[{'brand_name':'Unknown'}, {'manufacturer':'Other company'}, {'strength':'400 mg'}, {'active_ingredient':'Paracetamol'}, {'dosage_form':'capsule'}])
def test_different_product_details_are_inconclusive(public_source,updates):
    supplied=fields().model_copy(update=updates)
    result=online.search_package_reference(supplied)
    assert result.status=='not_found' and result.product is None


def test_multiple_strengths_are_not_an_unambiguous_product_match(public_source):
    public_source['html']='<table>'+row()+row(brand='BRUFEN TABLETS 400MG',composition='Each tablet contains: Ibuprofen 400mg.')+'</table>'
    supplied=fields(); supplied.strength=None
    assert online.search_package_reference(supplied).status=='not_found'


def test_duplicate_pack_sizes_do_not_create_ambiguity(public_source):
    public_source['html']='<table>'+row()+row()+'</table>'
    assert online.search_package_reference(fields()).status=='matched'


def test_plural_tablets_match_tablet_and_never_select_unknown_suspension(public_source):
    public_source['html']='<table>'+row()+row(brand='BRUFEN SUSPENSION',composition='Unsupported liquid declaration')+'</table>'
    supplied=fields(); supplied.dosage_form='Tablets'
    result=online.search_package_reference(supplied)
    assert result.status=='matched'
    assert result.product.brand_name=='BRUFEN TABLETS 200MG'
    assert result.product.strength=='200 mg'


def test_missing_source_strength_cannot_confirm_a_supplied_strength(public_source):
    public_source['html']='<table>'+row(composition='Unsupported tablet declaration')+'</table>'
    assert online.search_package_reference(fields()).status=='not_found'


def test_public_source_failure_is_safe_and_cached(public_source):
    public_source['fail']=True
    result=online.search_package_reference(fields())
    assert result.status=='unavailable' and not result.sources
    assert 'private internal error' not in result.summary
    assert online.search_package_reference(fields()).status=='unavailable'
    assert len(public_source['requests'])==1


def test_changed_search_form_is_reported_without_guessing(public_source):
    public_source['page']='<html>Unexpected page</html>'
    assert online.search_package_reference(fields()).status=='unavailable'


def test_bounded_source_response(public_source,monkeypatch):
    monkeypatch.setattr(online,'MAX_SOURCE_BYTES',10)
    assert online.search_package_reference(fields()).status=='unavailable'


def test_daily_quota_retry_time_is_not_replaced_with_one_minute():
    exc=errors.ClientError(429,{'error':{'message':'Daily quota exhausted','details':[
        {'violations':[{'quotaId':'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]},
        {'retryDelay':'25007s'},
    ]}})
    with pytest.raises(gemini_service.GeminiQuotaError) as raised:
        gemini_service._raise_provider_error(exc,'configured-model')
    assert raised.value.retry_after=='25007'
    assert 'daily free-tier limit' in raised.value.public_message
