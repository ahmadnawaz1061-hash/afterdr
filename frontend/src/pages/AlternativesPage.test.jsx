import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import catalog from '../../../backend/data/alternative_medicines_pk.json';
import AlternativesPage from './AlternativesPage';
import { getMedicineAlternatives, searchAlternativeMedicines } from '../services/alternativesApi';

vi.mock('../services/alternativesApi', () => ({ getMedicineAlternatives: vi.fn(), searchAlternativeMedicines: vi.fn() }));
const original = { id: 1, ...catalog.records[0], source_checked_at: catalog.source_checked_at, is_demo: false };
const candidate = { id: 2, ...catalog.records[1], source_checked_at: catalog.source_checked_at, is_demo: false, is_alternative: true,
  match_reasons: ['Same active ingredient(s)', 'Equivalent normalized strength', 'Same dosage form', 'Same route', 'Same release type'] };

beforeEach(() => {
  searchAlternativeMedicines.mockReset().mockResolvedValue([original]);
  getMedicineAlternatives.mockReset().mockResolvedValue([candidate]);
  vi.stubGlobal('requestAnimationFrame', (callback) => callback());
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function search(query = 'Panadol') {
  fireEvent.change(screen.getByLabelText('Brand or active ingredient'), { target: { value: query } });
  fireEvent.click(screen.getByRole('button', { name: 'Search medicines' }));
  return screen.findByRole('button', { name: 'Compare alternatives for Panadol' });
}

it('starts with guidance and no automatic requests or fictional records', () => {
  render(<AlternativesPage />);
  expect(searchAlternativeMedicines).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Search medicines' }).disabled).toBe(true);
  expect(screen.getByRole('complementary', { name: 'Substitution guidance' }).textContent).toContain('Confirm with your pharmacist');
  expect(screen.queryByText('Simulated demo data')).toBeNull();
});

it('searches, selects a product and shows source links and a side-by-side comparison', async () => {
  render(<AlternativesPage />);
  fireEvent.click(await search('  Panadol  '));
  expect(searchAlternativeMedicines).toHaveBeenCalledWith('  Panadol  ', expect.objectContaining({ signal: expect.any(AbortSignal) }));
  expect(getMedicineAlternatives).toHaveBeenCalledWith(1, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  const comparison = screen.getByRole('region', { name: '2. Potential alternatives' });
  expect(await within(comparison).findByRole('heading', { name: 'Provas' })).toBeTruthy();
  const comparisonDetails = within(comparison).getByText('Comparison details & source').closest('details');
  expect(comparisonDetails.open).toBe(false);
  fireEvent.click(within(comparison).getByText('Comparison details & source'));
  fireEvent.click(within(comparison).getByText('Medicine details & source'));
  expect(comparisonDetails.open).toBe(true);
  const table = within(comparison).getByRole('table');
  expect(within(table).getAllByRole('row')).toHaveLength(6);
  expect(within(comparison).getByText('Equivalent normalized strength')).toBeTruthy();
  expect(within(comparison).getByText(/This comparison is for information only/)).toBeTruthy();
  expect(within(comparison).getAllByRole('link', { name: 'View DRAP listing (opens a new tab)' })).toHaveLength(2);
  expect(comparison).toBe(document.activeElement);
});

it('shows loading and blocks duplicate search submissions', async () => {
  let resolve;
  searchAlternativeMedicines.mockReturnValue(new Promise((done) => { resolve = done; }));
  render(<AlternativesPage />);
  fireEvent.change(screen.getByLabelText('Brand or active ingredient'), { target: { value: 'Panadol' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search medicines' }));
  expect(screen.getByText('Searching the catalog...')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Search medicines' }).disabled).toBe(true);
  await act(async () => resolve([original]));
  expect(screen.getByRole('button', { name: 'Search medicines' }).disabled).toBe(false);
});

it('labels spelling suggestions and compares only the product the user selects', async () => {
  searchAlternativeMedicines.mockResolvedValue([{ ...original, similar_spelling: true }]);
  render(<AlternativesPage />);
  const result = await search('panadlo');
  expect(screen.getByText(/Showing similar spellings for/).textContent).toContain('panadlo');
  expect(getMedicineAlternatives).not.toHaveBeenCalled();
  fireEvent.click(result);
  expect(getMedicineAlternatives).toHaveBeenCalledWith(original.id, expect.any(Object));
  await screen.findByRole('heading', { name: 'Provas' });
});

it('handles unavailable search records and an empty Pakistan catalog', async () => {
  searchAlternativeMedicines.mockResolvedValue([]);
  render(<AlternativesPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Browse catalog' }));
  expect(await screen.findByText(/No Pakistan catalog records are available yet/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Brand or active ingredient'), { target: { value: 'Missing' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search medicines' }));
  expect(await screen.findByText(/A missing record does not mean the medicine is unregistered/)).toBeTruthy();
});

it('shows failed search details and retries the same term', async () => {
  searchAlternativeMedicines.mockRejectedValueOnce({ response: { data: { detail: 'Catalog temporarily unavailable.' } } }).mockResolvedValueOnce([original]);
  render(<AlternativesPage />);
  fireEvent.change(screen.getByLabelText('Brand or active ingredient'), { target: { value: 'Panadol' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search medicines' }));
  expect((await screen.findByRole('alert')).textContent).toContain('Catalog temporarily unavailable.');
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByRole('button', { name: 'Compare alternatives for Panadol' })).toBeTruthy();
  expect(searchAlternativeMedicines).toHaveBeenLastCalledWith('Panadol', expect.any(Object));
});

it('handles incomplete matching data without proposing a substitution', async () => {
  getMedicineAlternatives.mockResolvedValue([]);
  render(<AlternativesPage />);
  fireEvent.click(await search());
  expect(await screen.findByText('No matching candidates in this catalog')).toBeTruthy();
  expect(screen.getByText(/incomplete or unsupported information/)).toBeTruthy();
  expect(screen.queryByRole('table')).toBeNull();
});

it('retries failed alternatives for the same selected catalog ID', async () => {
  getMedicineAlternatives.mockRejectedValueOnce(new Error('Please restart the backend.')).mockResolvedValueOnce([candidate]);
  render(<AlternativesPage />);
  fireEvent.click(await search());
  expect((await screen.findByRole('alert')).textContent).toContain('Please restart the backend.');
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByRole('heading', { name: 'Provas' })).toBeTruthy();
  expect(getMedicineAlternatives).toHaveBeenLastCalledWith(1, expect.any(Object));
});

it('aborts and ignores outdated results after the search input changes', async () => {
  let resolve;
  searchAlternativeMedicines.mockReturnValue(new Promise((done) => { resolve = done; }));
  render(<AlternativesPage />);
  fireEvent.change(screen.getByLabelText('Brand or active ingredient'), { target: { value: 'Panadol' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search medicines' }));
  const signal = searchAlternativeMedicines.mock.calls[0][1].signal;
  fireEvent.change(screen.getByLabelText('Brand or active ingredient'), { target: { value: 'Provas' } });
  expect(signal.aborted).toBe(true);
  await act(async () => resolve([original]));
  expect(screen.queryByRole('button', { name: 'Compare alternatives for Panadol' })).toBeNull();
});

it('ignores a late comparison for a previously selected medicine', async () => {
  let resolveOld;
  searchAlternativeMedicines.mockResolvedValue([original, { ...candidate }]);
  getMedicineAlternatives.mockReturnValueOnce(new Promise((done) => { resolveOld = done; })).mockResolvedValueOnce([]);
  render(<AlternativesPage />);
  fireEvent.click(await search());
  fireEvent.click(screen.getByRole('button', { name: 'Compare alternatives for Provas' }));
  expect(await screen.findByText('No matching candidates in this catalog')).toBeTruthy();
  await act(async () => resolveOld([candidate]));
  expect(screen.queryByRole('table')).toBeNull();
});

it('aborts in-flight requests on unmount', async () => {
  searchAlternativeMedicines.mockReturnValue(new Promise(() => {}));
  const view = render(<AlternativesPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Browse catalog' }));
  const signal = searchAlternativeMedicines.mock.calls[0][1].signal;
  view.unmount();
  expect(signal.aborted).toBe(true);
});

it('does not render arbitrary external or unsafe catalog source links', async () => {
  searchAlternativeMedicines.mockResolvedValue([{ ...original, source_url: 'javascript:alert(1)', formulation_source_url: 'https://example.com/unverified' }]);
  render(<AlternativesPage />);
  await search();
  expect(screen.queryByRole('link')).toBeNull();
});

it('brings the comparison into view while loading and lets mobile users return to the results', async () => {
  const previous = Element.prototype.scrollIntoView;
  const scroll = vi.fn();
  Element.prototype.scrollIntoView = scroll;
  try {
    getMedicineAlternatives.mockReturnValue(new Promise(() => {}));
    render(<AlternativesPage />);
    fireEvent.click(await search());
    const comparison = screen.getByRole('region', { name: '2. Potential alternatives' });
    expect(document.activeElement).toBe(comparison);
    expect(scroll).toHaveBeenCalledWith({ block: 'start', behavior: 'instant' });
    expect(screen.getByText('Comparing documented attributes...')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Back to medicines' }));
    expect(document.activeElement).toBe(screen.getByRole('region', { name: 'Catalog results' }));
    expect(scroll).toHaveBeenLastCalledWith({ block: 'nearest', behavior: 'instant' });
  } finally {
    if (previous) Element.prototype.scrollIntoView = previous;
    else delete Element.prototype.scrollIntoView;
  }
});

const fullPage = [original, ...Array.from({ length: 9 }, (_, index) => ({ ...original, id: index + 10, brand_name: `Test product ${index}` }))];

it('loads the next page without losing the selection and hides the button at the end', async () => {
  searchAlternativeMedicines.mockResolvedValueOnce(fullPage).mockResolvedValueOnce([candidate]);
  getMedicineAlternatives.mockResolvedValue([]);
  render(<AlternativesPage />);
  fireEvent.click(await search());
  await screen.findByText('No matching candidates in this catalog');
  fireEvent.click(screen.getByRole('button', { name: 'Load more medicines' }));
  expect(await screen.findByRole('button', { name: 'Compare alternatives for Provas' })).toBeTruthy();
  expect(searchAlternativeMedicines).toHaveBeenLastCalledWith('Panadol', expect.objectContaining({ offset: 10 }));
  expect(screen.getByRole('button', { name: 'Compare alternatives for Panadol' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.queryByRole('button', { name: 'Load more medicines' })).toBeNull();
});

it('preserves earlier records when a later page fails and retries the same offset', async () => {
  searchAlternativeMedicines.mockResolvedValueOnce(fullPage).mockRejectedValueOnce(new Error('Connection interrupted')).mockResolvedValueOnce([candidate]);
  render(<AlternativesPage />);
  await search();
  fireEvent.click(screen.getByRole('button', { name: 'Load more medicines' }));
  expect((await screen.findByRole('alert')).textContent).toContain('Connection interrupted');
  expect(screen.getByRole('button', { name: 'Compare alternatives for Panadol' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  await screen.findByRole('button', { name: 'Compare alternatives for Provas' });
  expect(searchAlternativeMedicines.mock.calls.slice(1).map(([, options]) => options.offset)).toEqual([10, 10]);
  expect(screen.queryByRole('alert')).toBeNull();
});

it('ignores a late page after a new search starts', async () => {
  let resolvePage;
  searchAlternativeMedicines.mockResolvedValueOnce(fullPage)
    .mockReturnValueOnce(new Promise((done) => { resolvePage = done; }))
    .mockResolvedValueOnce([{ ...original, brand_name: 'New result' }]);
  render(<AlternativesPage />);
  await search();
  fireEvent.click(screen.getByRole('button', { name: 'Load more medicines' }));
  const signal = searchAlternativeMedicines.mock.calls[1][1].signal;
  fireEvent.change(screen.getByLabelText('Brand or active ingredient'), { target: { value: 'New' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search medicines' }));
  await screen.findByRole('button', { name: 'Compare alternatives for New result' });
  expect(signal.aborted).toBe(true);
  await act(async () => resolvePage([candidate]));
  expect(screen.queryByRole('button', { name: 'Compare alternatives for Provas' })).toBeNull();
});
