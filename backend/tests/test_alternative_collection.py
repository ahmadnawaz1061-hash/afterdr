"""Offline tests of source interpretation, with no website/network dependency."""

import json

import pytest

from scripts import collect_alternative_catalog as collector


def source_row(composition, product="Pyrol Tablet 500mg", registration="014891"):
    parser = collector.PriceTableParser()
    parser.feed(f'''<table><tbody><tr><td>
        <div class="text-sm font-medium text-gray-900">{product}</div>
        <div class="max-w-[200px] text-sm text-gray-500">{composition}</div>
        </td><td>{registration}</td><td><div class="text-sm text-gray-900">Semos Pharmaceuticals PVT LTD</div>
        <div class="text-sm text-gray-500">DML: 000335</div></td><td>generic</td><td>10</td><td>price</td><td>date</td></tr></tbody></table>''')
    assert len(parser.rows) == 1
    return parser.rows[0]


def test_source_fields_and_dot_leaders_are_parsed_without_inventing_route_or_release():
    record = collector.extract_record(source_row("Each tablet contains:- Paracetamol &#xfffd; 500mg"), "https://e.dra.gov.pk/public/price?page=516")
    assert record["registration_no"] == "014891"
    assert record["manufacturer"] == "Semos Pharmaceuticals PVT LTD"
    assert record["active_ingredient"] == "Paracetamol"
    assert record["strength"] == "500 mg"
    assert record["route"] == record["release_type"] == "unknown"
    assert "Paracetamol" in record["source_composition"]


@pytest.mark.parametrize("composition", [
    "Each tablet contains: Paracetamol 500mg + Caffeine 65mg",
    "Each tablet contains: Metformin HCl equivalent to Metformin 500mg",
    "Each tablet contains: Paracetamol approx 500mg",
    "Each tablet contains: Paracetamol 0mg",
    "Each tablet contains: Paracetamol 500mg and other active ingredients",
    "Each 5ml contains: Paracetamol 120mg",
    "Each tablet contains: Parac&#xfffd;tamol 500mg",
])
def test_ambiguous_or_unsupported_source_compositions_are_excluded(composition):
    assert collector.extract_record(source_row(composition), "https://e.dra.gov.pk/public/price?page=516") is None


def test_source_conflicting_product_form_is_excluded():
    assert collector.extract_record(source_row("Each tablet contains:Albendazole USP&#xfffd;.100mg", "Albendal Suspension", "019652"), "https://e.dra.gov.pk/public/price?page=522") is None


def test_specific_form_is_retained_from_product_name():
    record = collector.extract_record(source_row("Each Tablet contains:Deferasirox&#xfffd;&#xfffd;400mg", "Xefra 400mg Dispersible Tablets", "075072"), "https://e.dra.gov.pk/public/price?page=616")
    assert record["dosage_form"] == "dispersible tablet"


def test_rerun_with_target_already_met_preserves_catalog_and_audit(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"records": [{"registration_no": "014891"}], "collection": {"pages": [516]}}), encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(collector, "CATALOG_PATH", path)
    monkeypatch.setattr(collector.requests.Session, "get", lambda *a, **k: pytest.fail("Unexpected network request"))
    collector.collect(1, [516])
    assert path.read_bytes() == before


def test_insufficient_sources_leave_snapshot_unchanged(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"records": []}), encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    # A page with an internally conflicting form supplies no accepted records.
    row = source_row("Each tablet contains:Albendazole 100mg", "Albendal Suspension", "019652")
    class Parser:
        rows = [row]
        def feed(self, html):
            pass
    (cache / "price-522.html").write_text("cached page", encoding="utf-8")
    monkeypatch.setattr(collector, "CATALOG_PATH", path)
    monkeypatch.setattr(collector, "CACHE", cache)
    monkeypatch.setattr(collector, "PriceTableParser", Parser)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="left unchanged"):
        collector.collect(1, [522])
    assert path.read_bytes() == before


def test_expansion_deduplicates_packaging_and_preserves_previous_evidence_dates(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    original = {"registration_no": "000001", "source_checked_at": "2000-01-01", "source_composition": "Preserved manual evidence", "source_url": "https://e.dra.gov.pk/public/price?page=516"}
    previous_page = {"url": "https://e.dra.gov.pk/public/price?page=515"}
    path.write_text(json.dumps({"records": [original], "collection": {"pages": [previous_page], "manually_enriched": ["000001"]}}), encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "price-516.html").write_text("cached page", encoding="utf-8")
    first = source_row("Each tablet contains:Paracetamol 500mg")
    second = source_row("Each tablet contains:Paracetamol 500mg", "Advimol Tablets 500mg", "003216")
    class Parser:
        rows = [first, first, second]
        def feed(self, html):
            pass
    monkeypatch.setattr(collector, "CATALOG_PATH", path)
    monkeypatch.setattr(collector, "CACHE", cache)
    monkeypatch.setattr(collector, "PriceTableParser", Parser)
    collector.collect(3, [516])
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["records"][0] == original
    assert len({row["registration_no"] for row in result["records"]}) == 3
    assert result["collection"]["pages"][0] == previous_page
    assert result["collection"]["pages"][1]["duplicates"] == 1
    assert result["collection"]["manually_enriched"] == ["000001"]
