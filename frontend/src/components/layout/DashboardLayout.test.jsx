import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import DashboardLayout from './DashboardLayout';
import DashboardPage from '../../pages/DashboardPage';
import PrescriptionPage from '../../pages/PrescriptionPage';
import { getDashboard } from '../../services/api';

vi.mock('../../services/api', () => ({
  getDashboard: vi.fn(),
  extractPrescription: vi.fn(),
  savePrescription: vi.fn(),
}));

beforeEach(() => {
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  getDashboard.mockResolvedValue({
    patient: { id: 1, name: 'Test User' }, active_prescriptions: 0,
    today: { total_doses: 0, taken: 0, missed: 0, remaining: 0 },
    next_dose: null, recent_verifications: 0,
  });
});
afterEach(cleanup);

function renderLayout() {
  return render(<MemoryRouter initialEntries={['/dashboard']}><Routes>
    <Route element={<DashboardLayout />}>
      <Route index element={<h1>Welcome</h1>} />
      <Route path="dashboard" element={<DashboardPage />} />
      <Route path="prescription" element={<PrescriptionPage />} />
    </Route>
  </Routes></MemoryRouter>);
}

it('keeps the natural focus position on arrival so the skip link stays first', () => {
  renderLayout();
  expect(document.activeElement).toBe(document.body);
  expect(window.scrollTo).not.toHaveBeenCalled();
  expect(screen.getByRole('link', { name: 'Skip to main content' }).getAttribute('href')).toBe('#main-content');
});

it('returns focus to the menu button when navigation closes with Escape', () => {
  renderLayout();
  fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }));
  const welcome = screen.getByRole('link', { name: 'Welcome' });
  welcome.focus();
  fireEvent.keyDown(welcome, { key: 'Escape' });
  const toggle = screen.getByRole('button', { name: 'Open navigation' });
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  expect(document.activeElement).toBe(toggle);
});

it('closes the menu and resets scroll and focus when navigating through the navbar', () => {
  renderLayout();
  fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }));
  fireEvent.click(screen.getByRole('link', { name: 'MedCare AI home' }));
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Welcome');
  expect(screen.getByRole('button', { name: 'Open navigation' }).getAttribute('aria-expanded')).toBe('false');
  expect(document.activeElement).toBe(screen.getByRole('main'));
  expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: 'instant' });
});

it('shows account data without preview controls or sample records', async () => {
  renderLayout();
  expect(await screen.findByRole('heading', { name: 'Welcome, Test User' })).toBeTruthy();
  expect(screen.getByText('Active prescriptions')).toBeTruthy();
  expect(screen.getByRole('link', { name: /Taken today: 0/ }).getAttribute('href')).toBe('/scheduler');
  expect(screen.getByRole('link', { name: /Missed today: 0/ }).getAttribute('href')).toBe('/scheduler');
  expect(screen.getByRole('link', { name: 'Check a package' }).getAttribute('href')).toBe('/verification');
  expect(screen.queryByRole('button', { name: 'View sample' })).toBeNull();
});

it('refreshes dashboard totals without requiring a page reload', async () => {
  getDashboard
    .mockResolvedValueOnce({
      patient: { id: 1, name: 'Test User' }, active_prescriptions: 1,
      today: { total_doses: 2, taken: 0, missed: 0, remaining: 2 },
      next_dose: { medicine: 'Course medicine', time: '21:00' }, recent_verifications: 0,
    })
    .mockResolvedValueOnce({
      patient: { id: 1, name: 'Test User' }, active_prescriptions: 1,
      today: { total_doses: 2, taken: 1, missed: 1, remaining: 0 },
      next_dose: null, recent_verifications: 1,
    });
  renderLayout();
  expect(await screen.findByRole('link', { name: /Taken today: 0/ })).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'Refresh dashboard' }));

  await waitFor(() => expect(screen.getByRole('link', { name: /Taken today: 1/ })).toBeTruthy());
  expect(screen.getByRole('link', { name: /Missed today: 1/ })).toBeTruthy();
  expect(screen.getByRole('link', { name: /Still pending: 0/ })).toBeTruthy();
});
