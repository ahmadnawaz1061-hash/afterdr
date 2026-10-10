"""Collect a bounded DRAP price-index snapshot; never infer substitution eligibility.

Run from backend/: python -m scripts.collect_alternative_catalog --target 150
No API calls occur in the web application's request path. Saved raw pages are
research caches under the ignored .tools directory, not patient data.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
import time

import requests

from app.services.alternative_catalog import CATALOG_PATH


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT.parent / ".tools" / "module-c-catalog-research"
BASE_URL = "https://e.dra.gov.pk/public/price"


class PriceTableParser(HTMLParser):
    """Read product/registration/manufacturer cells, excluding packaging repeats."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.div_depth = 0
        self.capture = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = {"text": [], "divs": []}
        elif tag == "div" and self.cell is not None:
            self.div_depth += 1
            classes = dict(attrs).get("class", "")
            if self.capture is None and "text-sm" in classes:
                self.capture = {"depth": self.div_depth, "class": classes, "text": []}

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"].append(data)
            if self.capture is not None:
                self.capture["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "div" and self.cell is not None:
            if self.capture is not None and self.capture["depth"] == self.div_depth:
                self.cell["divs"].append((self.capture["class"], " ".join("".join(self.capture["text"]).split())))
                self.capture = None
            self.div_depth -= 1
        elif tag == "td" and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
            self.capture = None
            self.div_depth = 0
        elif tag == "tr" and self.row is not None:
            if len(self.row) == 7:
                self.rows.append(self.row)
            self.row = None


def extract_record(cells, source_url):
    products = cells[0]["divs"]
    brand = next((text for classes, text in products if "font-medium" in classes), "")
    composition = next((text for classes, text in products if "max-w-" in classes), "")
    registration = "".join(cells[1]["text"]).strip()
    manufacturer = next((text for classes, text in cells[2]["divs"] if "text-gray-900" in classes), "")
    if not re.fullmatch(r"\d{6}", registration) or not brand or not manufacturer:
        return None

    # Only unambiguous single-ingredient per-tablet/capsule declarations. The
    # original text is retained so extraction can be reviewed independently.
    form_match = re.match(
        r"Each\s+(?P<form>(?:(?:film[- ]?coated|uncoated|enteric[- ]?coated)\s+)?(?:tablet|capsule))\s+contains\s*[:.\-]*\s*(?P<body>.+)",
        composition, re.IGNORECASE,
    )
    if not form_match:
        return None
    form = " ".join(form_match["form"].lower().replace("-", " ").split())
    # Source errors occur: a suspension product can have a tablet composition.
    # Exclude conflicting forms instead of transcribing an internally wrong row.
    if re.search(r"\b(?:suspension|syrup|injection|solution|drops|cream|ointment|gel|powder)\b", brand, re.IGNORECASE):
        return None
    if ("tablet" in form and re.search(r"\bcapsules?\b", brand, re.IGNORECASE)) or (
        "capsule" in form and re.search(r"\btablets?\b", brand, re.IGNORECASE)
    ):
        return None
    if form == "tablet":
        descriptor = re.search(r"\b(dispersible|chewable|effervescent|sublingual|buccal)\s+tablets?\b", brand, re.IGNORECASE)
        if descriptor:
            form = f"{descriptor[1].lower()} tablet"
    body = form_match["body"]
    # DRAP sometimes publishes replacement characters in dot leaders. Allow
    # them only between the ingredient and numeric strength, never in names.
    match = re.fullmatch(
        r"(?P<ingredient>[A-Za-z][A-Za-z ()/,'\-]*?[A-Za-z)])(?:\s*[.\u2026\ufffd:\-]\s*|\s+)+"
        r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>mg|mcg|micrograms?|gm|g)\s*\.?",
        body, re.IGNORECASE,
    )
    if not match or float(match["amount"]) <= 0:
        return None
    ingredient = match["ingredient"].strip()
    if re.search(r"\b(?:equivalent|eq|each|contains|as|to|and|approx|approximately|about|range)\b", ingredient, re.IGNORECASE):
        return None  # salt/base equivalences need manual curation
    unit = match["unit"].lower()
    unit = "g" if unit == "gm" else "mcg" if unit.startswith("microgram") else unit
    return {
        "brand_name": brand,
        "active_ingredient": ingredient,
        "strength": f"{match['amount']} {unit}",
        "dosage_form": form,
        "route": "unknown",
        "release_type": "unknown",
        "manufacturer": manufacturer,
        "registration_no": registration,
        "data_source": "drap_pk",
        "source_url": source_url,
        "source_product_name": brand,
        "source_composition": composition,
        "evidence_note": "Composition, unit dosage form, company and registration are transcribed from the DRAP price index. Route and release are undocumented here; excluded from alternative matching pending product-specific evidence.",
    }


def collect(target, pages, refresh=False):
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    records = list(catalog["records"])
    if len(records) >= target:
        print(f"Catalog already contains {len(records)} records; preserved existing snapshot and audit.")
        return
    by_registration = {r["registration_no"]: r for r in records}
    audit = []
    CACHE.mkdir(parents=True, exist_ok=True)
    with requests.Session() as http:
        for page in pages:
            if len(records) >= target:
                break
            url = f"{BASE_URL}?page={page}"
            cache_path = CACHE / f"price-{page}.html"
            if refresh or not cache_path.exists():
                response = http.get(url, timeout=(15, 45))
                response.raise_for_status()
                html = response.content.decode("utf-8")
                cache_path.write_text(html, encoding="utf-8")
                time.sleep(0.3)
            else:
                html = cache_path.read_text(encoding="utf-8")
            checked_at = datetime.fromtimestamp(cache_path.stat().st_mtime, timezone.utc).date().isoformat()
            parser = PriceTableParser()
            parser.feed(html)
            if not parser.rows:
                raise ValueError(f"No DRAP table rows at {url}; catalog left unchanged")
            added = ambiguous = duplicates = 0
            for row in parser.rows:
                record = extract_record(row, url)
                if record is None:
                    ambiguous += 1
                    continue
                existing = by_registration.get(record["registration_no"])
                if existing:
                    duplicates += 1
                    # Existing hand-curated records take precedence. Duplicate
                    # packaging rows never count as new medicines.
                    continue
                records.append(record)
                record["source_checked_at"] = checked_at
                by_registration[record["registration_no"]] = record
                added += 1
                if len(records) == target:
                    break
            audit.append({"url": url, "source_checked_at": checked_at, "rows": len(parser.rows), "added": added, "duplicates": duplicates, "unparsed": ambiguous})
            print(f"Page {page}: +{added}, {len(records)} unique records", flush=True)
    if len(records) < target:
        raise ValueError(f"Only {len(records)} records available from selected pages; catalog left unchanged")
    catalog["records"] = records
    previous_collection = catalog.get("collection", {})
    catalog["collection"] = {
        **previous_collection,
        "collected_at": date.today().isoformat(),
        "method": "Bounded DRAP HTML price-index extraction; unique registrations; conservative single-ingredient tablet/capsule parsing. Original manually curated records retained.",
        "pages": previous_collection.get("pages", []) + audit,
        "runtime_external_api": False,
    }
    # Write beside the snapshot and replace it atomically. Preserve source dates
    # and previous review audit; collecting more rows does not refresh old ones.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=CATALOG_PATH.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(CATALOG_PATH)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"Saved {len(records)} unique DRAP records ({CATALOG_PATH.stat().st_size:,} bytes).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=150)
    parser.add_argument("--pages", nargs="+", type=int, default=list(range(510, 531)) + list(range(590, 621)) + list(range(690, 711)))
    parser.add_argument("--refresh", action="store_true", help="Refetch public pages instead of reusing the research cache")
    args = parser.parse_args()
    if not 1 <= args.target <= 1000 or any(page < 1 for page in args.pages):
        parser.error("Target must be 1..1000 and page numbers must be positive")
    collect(args.target, args.pages, args.refresh)


if __name__ == "__main__":
    main()
