import pytest

from app.models import Medicine
from app.services.alternative_catalog import load_catalog
from app.services.medicine_search import rank_medicines


def catalog():
    return [Medicine(**row) for row in load_catalog()['records']]


@pytest.mark.parametrize('query,expected', [
    ('panadlo', 'Panadol'), ('panadoll', 'Panadol'),
    ('brufn 400mg', 'BRUFEN TABLETS 400MG'),
    ('glucophge 500mg', 'Glucophage Tablets'),
    ('paracetmol', 'Panadol'),
])
def test_typo_and_transposition_suggestions(query, expected):
    matches = rank_medicines(catalog(), query)
    assert matches and all(match.similar_spelling for match in matches)
    assert expected in [match.medicine.brand_name for match in matches]


@pytest.mark.parametrize('query', ['Panadol', '  PANADOL  ', 'panadol500mg', 'acetaminophen'])
def test_direct_searches_and_aliases_do_not_claim_spelling_correction(query):
    matches = rank_medicines(catalog(), query)
    assert matches and matches[0].medicine.brand_name in {'Panadol', 'Calpol', 'Fevadol', 'Provas'}
    assert not any(match.similar_spelling for match in matches)


@pytest.mark.parametrize('query', ['Panadol 50mg', 'panadlo 50mg', 'Concor 25mg', 'Concor .5mg', '%', 'zzzzzzzzzz', 'pna'])
def test_wrong_doses_garbage_and_short_typos_return_no_results(query):
    assert rank_medicines(catalog(), query) == []


def test_decimal_strengths_remain_distinct():
    matches = rank_medicines(catalog(), 'Concor 2.5mg')
    assert len(matches) == 1
    assert matches[0].medicine.strength == '2.5 mg'
    matches = rank_medicines(catalog(), 'Lanoxin .25mg')
    assert len(matches) == 1 and matches[0].medicine.strength == '0.25 mg'


def test_direct_match_wins_over_lookalike_brand():
    medicines = [Medicine(brand_name=name, active_ingredient='unknown', strength='10 mg', dosage_form='tablet', route='unknown')
                 for name in ['Panadol', 'Panadol Extra', 'Penadol']]
    matches = rank_medicines(medicines, 'Panadol')
    assert matches[0].medicine.brand_name == 'Panadol'
    assert 'Penadol' not in [match.medicine.brand_name for match in matches]
    assert not any(match.similar_spelling for match in matches)


@pytest.mark.parametrize('query', [
    'Panadol', 'Calpol', 'Augmentin', 'Amoxil', 'Brufen', 'Disprin', 'Flagyl',
    'Risek', 'Losec', 'Claritek', 'Azomax', 'Zithromax', 'Ciproxin', 'Cefspan',
    'Glucophage', 'Norvasc', 'Cozaar', 'Concor', 'Lipitor', 'Maxolon', 'Imodium',
    'Vermox', 'Deltacortril', 'Zyloric', 'Thyroxine', 'Inderal', 'Ventolin',
    'Septran', 'Lasix', 'Aldactone', 'Epival', 'Ascard', 'Loprin', 'Plavix',
    'Lanoxin', 'Folic acid',
])
def test_familiar_brand_and_ingredient_coverage(query):
    matches = rank_medicines(catalog(), query)
    assert matches and not any(match.similar_spelling for match in matches)
