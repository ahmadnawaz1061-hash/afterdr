import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import LandingPage from './LandingPage';
import { searchMedicine } from '../services/api';
import { demoCatalog } from '../mocks/demoData';

vi.mock('../services/api', () => ({ searchMedicine: vi.fn(), USE_MOCKS: true }));

beforeEach(() => { searchMedicine.mockReset(); });
afterEach(cleanup);

function renderLanding() {
  return render(<MemoryRouter><Routes>
    <Route path="/" element={<LandingPage />} />
    <Route path="/dashboard" element={<h1>Dashboard destination</h1>} />
    <Route path="/register" element={<h1>Create account destination</h1>} />
  </Routes></MemoryRouter>);
}

it('shows the hero and five feature links without requesting data on arrival', () => {
  renderLanding();
  expect(screen.getByRole('heading', { level: 1 }).textContent).toContain('Your next step,');
  const features = screen.getByRole('region', { name: 'Support for each part of your medicine journey.' });
  expect(within(features).getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual([
    '/prescription', '/scheduler', '/alternatives', '/verification', '/reporting',
  ]);
  expect(screen.getByText('Confirm with your pharmacist or prescriber before substituting.')).toBeTruthy();
  expect(screen.getByText('DRAFT — NOT SUBMITTED')).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Explore the five tools' }).getAttribute('href')).toBe('#landing-features');
  expect(searchMedicine).not.toHaveBeenCalled();
  expect(screen.queryByLabelText('Preview state')).toBeNull();
});

it('opens account registration from the landing call to action', () => {
  renderLanding();
  fireEvent.click(screen.getByRole('link', { name: 'Create your account' }));
  expect(screen.getByRole('heading', { name: 'Create account destination' })).toBeTruthy();
});

it('announces loading before showing successful results, each with a demo badge', async () => {
  let resolveRequest;
  searchMedicine.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve; }));
  renderLanding();
  const loadButton = screen.getByRole('button', { name: 'Load catalog preview' });
  loadButton.focus();
  fireEvent.click(loadButton);
  expect(searchMedicine).toHaveBeenCalledWith('');
  expect(document.activeElement).toBe(loadButton);
  expect(loadButton.getAttribute('aria-disabled')).toBe('true');
  fireEvent.click(loadButton);
  expect(searchMedicine).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('status').textContent).toContain('Loading the catalog');
  expect(screen.getByRole('status').getAttribute('aria-live')).toBe('polite');
  expect(screen.queryByRole('button', { name: 'Load catalog preview' })).toBeNull();
  await act(async () => resolveRequest(demoCatalog));
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Refresh catalog' }));
  expect(screen.getByRole('status').textContent).toBe('Showing 3 catalog entries.');
  for (const medicine of demoCatalog) {
    const row = screen.getByRole('heading', { name: medicine.brand_name }).closest('li');
    expect(within(row).getByText('Simulated demo data')).toBeTruthy();
    expect(within(row).getByText(medicine.strength)).toBeTruthy();
  }
});

it('handles an empty catalog and allows refreshing it', async () => {
  searchMedicine.mockResolvedValueOnce([]).mockResolvedValueOnce(demoCatalog);
  renderLanding();
  fireEvent.click(screen.getByRole('button', { name: 'Load catalog preview' }));
  expect(await screen.findByText('No medicines are available to preview yet.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Refresh catalog' }));
  expect(await screen.findByRole('heading', { name: demoCatalog[0].brand_name })).toBeTruthy();
  expect(searchMedicine).toHaveBeenCalledTimes(2);
});

it('announces failure and retries while preserving the account entry link', async () => {
  searchMedicine.mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValueOnce(demoCatalog);
  renderLanding();
  fireEvent.click(screen.getByRole('button', { name: 'Load catalog preview' }));
  expect((await screen.findByRole('alert')).textContent).toContain('The catalog could not be loaded');
  expect(screen.getByRole('link', { name: 'Create your account' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByRole('heading', { name: demoCatalog[0].brand_name })).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
});

it.each([null, {}, [null]])('handles malformed catalog data as an error', async (result) => {
  searchMedicine.mockResolvedValue(result);
  renderLanding();
  fireEvent.click(screen.getByRole('button', { name: 'Load catalog preview' }));
  expect((await screen.findByRole('alert')).textContent).toContain('The catalog could not be loaded');
});

it('ignores a catalog response after navigation away', async () => {
  let resolveRequest;
  searchMedicine.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve; }));
  renderLanding();
  fireEvent.click(screen.getByRole('button', { name: 'Load catalog preview' }));
  fireEvent.click(screen.getByRole('link', { name: 'Create your account' }));
  await act(async () => resolveRequest(demoCatalog));
  expect(screen.getByRole('heading', { name: 'Create account destination' })).toBeTruthy();
  expect(screen.queryByText(demoCatalog[0].brand_name)).toBeNull();
});
