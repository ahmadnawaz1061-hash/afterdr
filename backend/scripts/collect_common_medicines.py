"""Collect public DRAP search evidence for review, without changing the catalog."""
import argparse
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import requests
from scripts.collect_alternative_catalog import PriceTableParser

CACHE = Path(__file__).resolve().parents[2] / '.tools' / 'common-medicines'
QUERIES = (
    'Augmentin', 'Amoxil', 'Brufen', 'Ponstan', 'Disprin', 'Flagyl',
    'Risek', 'Losec', 'Nexum', 'Nexium', 'Zyrtec', 'Rigix', 'Telfast',
    'Claritek', 'Azomax', 'Zithromax', 'Ciproxin', 'Ciprofloxacin',
    'Cefspan', 'Suprax', 'Velosef', 'Glucophage', 'Getryl', 'Amaryl',
    'Norvasc', 'Exforge', 'Cozaar', 'Concor', 'Tenormin', 'Lipitor',
    'Rovista', 'Crestor', 'Motilium', 'Maxolon', 'Imodium', 'Buscopan',
    'Duspatalin', 'No Spa', 'Voltaren', 'Cataflam', 'Arinac', 'Zentel',
    'Vermox', 'Deltacortril', 'Surbex', 'Serc', 'Xyzal', 'Zyloric',
    'Thyroxine', 'Inderal', 'Ventolin', 'Montika', 'Singulair', 'Calpol',
)

def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument('--queries', nargs='+', default=QUERIES)
    args = arguments.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    collected = []
    with requests.Session() as http:
        for query in args.queries:
            path = CACHE / (query.lower().replace(' ', '-') + '.html')
            if not path.exists():
                page = http.get('https://e.dra.gov.pk/public/price', timeout=30)
                page.raise_for_status()
                token_match = re.search(r'name="_token" value="([^"]+)"', page.text)
                if token_match is None:
                    raise ValueError('DRAP search form changed; no source records imported')
                token = token_match.group(1)
                response = http.post('https://e.dra.gov.pk/public/price/find',
                                     data={'_token': token, 'query': query}, timeout=30)
                response.raise_for_status()
                path.write_text(response.text, encoding='utf-8')
            parser = PriceTableParser()
            parser.feed(path.read_text(encoding='utf-8'))
            seen = set()
            for row in parser.rows:
                registration = ''.join(row[1]['text']).strip()
                if registration in seen or not re.fullmatch(r'\d{6}', registration):
                    continue
                seen.add(registration)
                def product(part):
                    return next((text for classes, text in row[0]['divs'] if part in classes), '')
                collected.append({'query': query, 'source_url': 'https://e.dra.gov.pk/public/price',
                    'source_checked_at': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat(),
                    'brand_name': product('font-medium'),
                    'source_composition': product('max-w-'), 'registration_no': registration,
                    'manufacturer': next((text for classes, text in row[2]['divs'] if 'text-gray-900' in classes), '')})
            print(f'{query}: {len(seen)} source records', flush=True)
    output = CACHE / 'records.json'
    previous = json.loads(output.read_text(encoding='utf-8')) if output.exists() else []
    retained = [row for row in previous if row['query'] not in args.queries]
    output.write_text(json.dumps(retained + collected, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
