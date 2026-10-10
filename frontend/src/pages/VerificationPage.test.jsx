import { act, cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, it, expect, beforeEach, afterEach } from 'vitest';
import VerificationPage from './VerificationPage';
import { analyzePackage, reanalyzeVerification, listVerifications, getVerification } from '../services/api';
import { createPackagingDemo } from '../mocks/packagingDemo';

const navigate = vi.fn();
vi.mock('react-router-dom', async () => ({ ...await vi.importActual('react-router-dom'), useNavigate: () => navigate }));
vi.mock('../services/api', () => ({ analyzePackage: vi.fn(), reanalyzeVerification: vi.fn(), listVerifications: vi.fn(), getVerification: vi.fn() }));

const png = () => new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 0])], 'front.png', { type: 'image/png' });
const showPage = () => render(<MemoryRouter><VerificationPage /></MemoryRouter>);
async function chooseFront() {
  fireEvent.change(screen.getByLabelText('Front of pack photograph'), { target: { files: [png()] } });
  await screen.findByAltText('Front of pack preview');
}
async function analyze() {
  await chooseFront();
  fireEvent.click(screen.getByRole('button', { name: 'Analyze packaging' }));
  return screen.findByRole('heading', { name: 'Looks consistent with an authentic product' });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 700, height: 500, close: vi.fn() }));
  URL.createObjectURL = vi.fn().mockReturnValue('blob:preview');
  URL.revokeObjectURL = vi.fn();
  listVerifications.mockResolvedValue([]);
  analyzePackage.mockResolvedValue(createPackagingDemo('consistent', {}, 10));
  reanalyzeVerification.mockResolvedValue(createPackagingDemo('consistent', { brand_name: 'Corrected name' }, 11));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('requires a front photo and removes fabricated production samples', () => {
  showPage();
  expect(screen.getByRole('button', { name: 'Analyze packaging' }).disabled).toBe(true);
  expect(screen.getByRole('heading', { name: 'Check if your medicine looks authentic' })).toBeTruthy();
  expect(screen.queryByText(/Quick Demo Packaging Samples/)).toBeNull();
  expect(screen.queryByText(/Pakistan DRAP Verified Catalog/)).toBeNull();
  expect(screen.queryByText(/Recent checks/)).toBeNull();
});

it('previews, replaces and removes images with an accessible control', async () => {
  showPage(); await chooseFront();
  expect(screen.getByRole('button', { name: 'Analyze packaging' }).disabled).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Remove Front of pack photo' }));
  expect(screen.queryByAltText('Front of pack preview')).toBeNull();
  expect(screen.getByRole('button', { name: 'Analyze packaging' }).disabled).toBe(true);
  expect(URL.revokeObjectURL).toHaveBeenCalled();
});

it('rejects invalid content before enabling analysis', async () => {
  showPage();
  fireEvent.change(screen.getByLabelText('Front of pack photograph'), { target: { files: [new File(['not png'], 'misleading.png', { type: 'image/png' })] } });
  expect((await screen.findByRole('alert')).textContent).toContain('not a PNG or JPEG');
  expect(screen.getByRole('button', { name: 'Analyze packaging' }).disabled).toBe(true);
});

it('rejects oversized images and excessive dimensions', async () => {
  showPage();
  fireEvent.change(screen.getByLabelText('Front of pack photograph'), { target: { files: [new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' })] } });
  expect((await screen.findByRole('alert')).textContent).toContain('5 MB');
  createImageBitmap.mockResolvedValueOnce({ width: 6001, height: 800, close: vi.fn() });
  fireEvent.change(screen.getByLabelText('Front of pack photograph'), { target: { files: [png()] } });
  expect((await screen.findByRole('alert')).textContent).toContain('6000');
});

it('submits multiple photos with manual corrections and no trusted-reference upload', async () => {
  showPage(); await chooseFront();
  fireEvent.change(screen.getByLabelText('Back or side photograph'), { target: { files: [png()] } });
  await screen.findByAltText('Back or side preview');
  fireEvent.click(screen.getByText('Correct the medicine details'));
  fireEvent.change(screen.getByLabelText('Brand name'), { target: { value: 'Reviewed brand' } });
  fireEvent.click(screen.getByRole('button', { name: 'Analyze packaging' }));
  await screen.findByRole('heading', { name: 'Looks consistent with an authentic product' });
  expect(analyzePackage).toHaveBeenCalledTimes(1);
  expect(analyzePackage.mock.calls[0][0]).toHaveLength(2);
  expect(analyzePackage.mock.calls[0][1].fields.brand_name).toBe('Reviewed brand');
  expect(screen.queryByText('Compare with a pack you trust')).toBeNull();
  expect(analyzePackage.mock.calls[0][1].trustedReference).toBeUndefined();
});

it('announces processing, cancels and ignores a late response', async () => {
  let resolve;
  analyzePackage.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
  showPage(); await chooseFront();
  fireEvent.click(screen.getByRole('button', { name: 'Analyze packaging' }));
  await waitFor(() => expect(analyzePackage).toHaveBeenCalled());
  expect(screen.getByText(/Reading packaging text and inspecting visual details…/)).toBeTruthy();
  const signal = analyzePackage.mock.calls[0][1].signal;
  fireEvent.click(screen.getByRole('button', { name: 'Cancel analysis' }));
  expect(signal.aborted).toBe(true);
  await act(async () => resolve(createPackagingDemo()));
  expect(screen.queryByRole('heading', { name: 'Looks consistent with an authentic product' })).toBeNull();
});

it.each([['consistent', 'Looks consistent with an authentic product'], ['suspicious_lookalike', 'Suspicious: possible knockoff or lookalike'], ['unclear_image', "Can't tell from these photos"]])('renders the %s verdict with the simulation badge', async (scenario, label) => {
  analyzePackage.mockResolvedValueOnce(createPackagingDemo(scenario));
  showPage(); await chooseFront(); fireEvent.click(screen.getByRole('button', { name: 'Analyze packaging' }));
  expect(await screen.findByRole('heading', { name: label })).toBeTruthy();
  expect(screen.getAllByText('Simulated demo data').length).toBeGreaterThan(0);
  expect(screen.queryByText('GENUINE')).toBeNull();
  if (scenario === 'unclear_image') expect(screen.getByText('Insufficient evidence for a score')).toBeTruthy();
});

it('keeps the demo badge absent for real evidence', async () => {
  const result = createPackagingDemo(); result.simulated = false;
  analyzePackage.mockResolvedValueOnce(result);
  showPage(); await analyze();
  expect(screen.queryByText('Simulated demo data')).toBeNull();
});

it('edits extracted fields through reanalysis without resubmitting photos', async () => {
  showPage(); await analyze();
  fireEvent.change(screen.getByLabelText('Brand'), { target: { value: 'Corrected name' } });
  fireEvent.click(screen.getByRole('button', { name: 'Update Assessment' }));
  await screen.findByDisplayValue('Corrected name');
  expect(reanalyzeVerification).toHaveBeenCalledWith(10, { brand_name: 'Corrected name' }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  expect(analyzePackage).toHaveBeenCalledTimes(1);
});

it('provides retry and different-photo actions after an error', async () => {
  analyzePackage.mockRejectedValueOnce(new Error('Gemini rate limit reached'));
  showPage(); await chooseFront(); fireEvent.click(screen.getByRole('button', { name: 'Analyze packaging' }));
  expect((await screen.findByRole('alert')).textContent).toContain('Gemini rate limit');
  expect(screen.getByRole('button', { name: 'Use Different Photos' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  await screen.findByRole('heading', { name: 'Looks consistent with an authentic product' });
});

it('prepares a report for the selected saved check and can start another', async () => {
  showPage(); await analyze();
  fireEvent.click(screen.getByRole('button', { name: 'Prepare a report draft' }));
  expect(navigate).toHaveBeenCalledWith('/reporting?verification_id=10');
  fireEvent.click(screen.getByRole('button', { name: 'Check another medicine' }));
  expect(screen.getByRole('button', { name: 'Analyze packaging' }).disabled).toBe(true);
  expect(screen.queryByAltText('Front of pack preview')).toBeNull();
});

it('loads recent checks without an ordinary scenario selector', async () => {
  listVerifications.mockResolvedValueOnce([{ verification_id: 20, brand_name: 'Saved brand', status_label: "Can't tell from these photos", simulated: false }]);
  getVerification.mockResolvedValueOnce(createPackagingDemo('unclear_image', {}, 20));
  showPage(); const summary = await screen.findByText('Recent checks (1)');
  expect(summary.closest('details').open).toBe(false);
  fireEvent.click(summary); fireEvent.click(screen.getByRole('button', { name: /Saved brand/ }));
  await screen.findByRole('heading', { name: "Can't tell from these photos" });
  expect(screen.queryByRole('combobox')).toBeNull();
});


it('shows sourced internet matches separately from extracted medicine details', async () => {
  const result = createPackagingDemo('consistent', { brand_name: 'Brufen' }, 20);
  result.online_lookup = { status: 'matched', summary: 'Product details matched in the live index.', sources: [{ title: 'DRAP product index', url: 'https://e.dra.gov.pk/public/price' }], product: { brand_name: 'BRUFEN TABLETS 200MG', manufacturer: 'Abbott', active_ingredient: 'Ibuprofen', strength: '200 mg', dosage_form: 'tablet' } };
  analyzePackage.mockResolvedValueOnce(result);
  showPage(); await analyze();
  expect(screen.getByText('Product details match')).toBeTruthy();
  expect(screen.getByRole('link', { name: 'DRAP product index (opens a new tab)' }).getAttribute('href')).toBe('https://e.dra.gov.pk/public/price');
  expect(screen.getByLabelText('Brand').value).toBe('Brufen');
});

it('retains assessment and editable details when the internet lookup fails', async () => {
  const result = createPackagingDemo('consistent', {}, 20);
  result.online_lookup = { status: 'unavailable', summary: 'The online source is unavailable.', sources: [], product: null };
  analyzePackage.mockResolvedValueOnce(result);
  showPage(); await analyze();
  expect(screen.getByText('Search unavailable')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Update Assessment' })).toBeTruthy();
});
