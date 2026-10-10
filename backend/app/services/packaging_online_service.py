"""Live, bounded product searches in DRAP's public online price index.

Search results establish documented product identity, not physical authenticity
or current regulatory validity. No model, external API key, or guessed facts.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from threading import Lock
import time

import httpx

from app.services.packaging_contracts import PackagingFields, OnlineLookup, OnlineSource
from app.services.packaging_reference import brand_key, normalize_manufacturer, manufacturer_matches, normalize_name
from app.services.alternative_service import normalize_matching_strength

BASE_URL = 'https://e.dra.gov.pk/public/price'
MAX_SOURCE_BYTES = 2 * 1024 * 1024
_cache = {}
_cache_lock = Lock()


class ProductTableParser(HTMLParser):
    """Capture source cells and nested label text without executing HTML."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = self.cell = self.capture = None
        self.div_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag == 'td' and self.row is not None:
            self.cell = {'text': [], 'divs': []}
        elif tag == 'div' and self.cell is not None:
            self.div_depth += 1
            classes = dict(attrs).get('class', '')
            if self.capture is None and 'text-sm' in classes:
                self.capture = {'depth': self.div_depth, 'class': classes, 'text': []}

    def handle_data(self, data):
        if self.cell is not None:
            self.cell['text'].append(data)
            if self.capture is not None:
                self.capture['text'].append(data)

    def handle_endtag(self, tag):
        if tag == 'div' and self.cell is not None:
            if self.capture is not None and self.capture['depth'] == self.div_depth:
                self.cell['divs'].append((self.capture['class'], ' '.join(''.join(self.capture['text']).split())))
                self.capture = None
            self.div_depth -= 1
        elif tag == 'td' and self.cell is not None:
            self.row.append(self.cell)
            self.cell = self.capture = None
            self.div_depth = 0
        elif tag == 'tr' and self.row is not None:
            if len(self.row) == 7:
                self.rows.append(self.row)
            self.row = None


def _bounded_page(client, method, url, **kwargs):
    with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        pieces, size = [], 0
        for piece in response.iter_bytes():
            size += len(piece)
            if size > MAX_SOURCE_BYTES:
                raise ValueError('Product source exceeded the response limit')
            pieces.append(piece)
        return b''.join(pieces).decode('utf-8', errors='replace')


def _products(html):
    parser = ProductTableParser()
    parser.feed(html)
    products = []
    seen = set()
    for row in parser.rows:
        def text_part(cell, marker):
            return next((text for classes, text in row[cell]['divs'] if marker in classes), None)
        brand = text_part(0, 'font-medium')
        manufacturer = text_part(2, 'text-gray-900')
        registration = ''.join(row[1]['text']).strip()
        composition = text_part(0, 'max-w-') or ''
        if not brand or not manufacturer or not re.fullmatch(r'\d{6}', registration):
            continue
        identity = (brand, manufacturer, composition)
        if identity in seen:
            continue
        seen.add(identity)
        # Extract only unambiguous declarations, leaving all other fields null.
        declaration = re.fullmatch(r'Each\s+(tablet|capsule)\s+contains\s*:\s*([A-Za-z][A-Za-z ()\-]*?)\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g)\s*\.?', composition, re.I)
        source_form = re.search(r'\b(tablets?|capsules?|suspension|syrup|injection|cream|gel|drops)\b', brand, re.I)
        form = declaration.group(1).lower() if declaration else _form(source_form.group(1)) if source_form else None
        if form and re.search(r'\b(suspension|syrup|injection|cream|gel)\b', brand, re.I):
            declaration = None
            form = _form(source_form.group(1)) if source_form else None
        products.append(PackagingFields(brand_name=brand, manufacturer=manufacturer,
            active_ingredient=declaration.group(2).strip() if declaration else None,
            strength=f'{declaration.group(3)} {declaration.group(4).lower()}' if declaration else None,
            dosage_form=form, pack_type=None))
    return products, bool(parser.rows)


def _form(value):
    return re.sub(r'\b(tablets|capsules)\b', lambda match: match.group(1)[:-1], normalize_name(value))


def search_package_reference(fields):
    if not fields.brand_name or not brand_key(fields.brand_name):
        return OnlineLookup(summary='Enter a readable brand name to search online product references.')
    # Canonicalize source query descriptors, not spelling: unknown names remain unknown.
    query = brand_key(fields.brand_name)
    key = tuple(getattr(fields, name) for name in ('brand_name', 'manufacturer', 'active_ingredient', 'strength', 'dosage_form'))
    now = time.monotonic()
    with _cache_lock:
        saved = _cache.get(key)
        if saved and saved[0] > now:
            return saved[1].model_copy(deep=True)
    checked = datetime.now(timezone.utc).isoformat()
    try:
        with httpx.Client(timeout=httpx.Timeout(10, connect=4), follow_redirects=False) as client:
            page = _bounded_page(client, 'GET', BASE_URL)
            token = re.search(r'name=["\']_token["\']\s+value=["\']([^"\']+)["\']', page)
            if not token:
                raise ValueError('Public product search form is unavailable')
            html = _bounded_page(client, 'POST', BASE_URL + '/find', data={'_token': token.group(1), 'query': query})
        products, table_found = _products(html)
        if not table_found and not re.search(r'no\s+(?:products|results|records|data)\s+found', html, re.I):
            raise ValueError('Product search response is unrecognized')
        named = [p for p in products if brand_key(p.brand_name) == brand_key(fields.brand_name)]
        matches = []
        for product in named:
            if fields.manufacturer and not manufacturer_matches(fields.manufacturer, product.manufacturer):
                continue
            if fields.active_ingredient and (not product.active_ingredient or normalize_name(fields.active_ingredient) != normalize_name(product.active_ingredient)):
                continue
            if fields.strength and (not product.strength or normalize_matching_strength(fields.strength) is None or normalize_matching_strength(fields.strength) != normalize_matching_strength(product.strength)):
                continue
            if fields.dosage_form and (not product.dosage_form or _form(fields.dosage_form) not in _form(product.dosage_form)):
                continue
            if fields.manufacturer or (fields.active_ingredient and fields.strength and product.active_ingredient and product.strength):
                matches.append(product)
        # Multiple forms/strengths cannot establish which product is represented.
        unique = {p.model_dump_json(): p for p in matches}
        product = next(iter(unique.values())) if len(unique) == 1 else None
        result = OnlineLookup(status='matched' if product else 'not_found', query=query,
            summary='Matching product details were found in DRAP’s live public price index. This identifies a documented product, not the physical pack.' if product else 'No unambiguous product match was found for the supplied details. Missing records, multiple formulations or different details are inconclusive.',
            product=product, sources=[OnlineSource(title='DRAP Pharmaceutical Product Price Index — search for ' + query, url=BASE_URL)], searched_at=checked)
    except (httpx.HTTPError, ValueError, TypeError):
        result = OnlineLookup(status='unavailable', query=query, summary='DRAP’s online product search is temporarily unavailable. The packaging assessment is retained; no internet match is claimed.', searched_at=checked)
    with _cache_lock:
        for existing in list(_cache):
            if _cache[existing][0] <= now:
                del _cache[existing]
        if len(_cache) >= 128:
            del _cache[next(iter(_cache))]
        _cache[key] = (now + (60 if result.status == 'unavailable' else 900), result.model_copy(deep=True))
    return result
