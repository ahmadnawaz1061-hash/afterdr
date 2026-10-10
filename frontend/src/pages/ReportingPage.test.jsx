import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import ReportingPage from './ReportingPage';
import { getVerification, createReportDraft, downloadReportDraft } from '../services/api';
import { createPackagingDemo } from '../mocks/packagingDemo';
vi.mock('../services/api', () => ({ getVerification: vi.fn(), createReportDraft: vi.fn(), downloadReportDraft: vi.fn() }));
beforeEach(() => { vi.clearAllMocks(); vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {}); getVerification.mockResolvedValue(createPackagingDemo('suspicious_lookalike', {}, 42)); createReportDraft.mockResolvedValue({ report_id: 5, status: 'draft_not_submitted' }); downloadReportDraft.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' })); URL.createObjectURL = vi.fn().mockReturnValue('blob:pdf'); URL.revokeObjectURL = vi.fn(); });
afterEach(cleanup);

it('offers the packaging-check entry point without an assessment', () => {
  render(<MemoryRouter><ReportingPage /></MemoryRouter>);
  expect(screen.getByRole('link', { name: 'Open Medicine Packaging Check' }).getAttribute('href')).toBe('/verification');
});

it('shows evidence, saves a draft and downloads its PDF', async () => {
  render(<MemoryRouter initialEntries={['/reporting?verification_id=42']}><ReportingPage /></MemoryRouter>);
  await screen.findByText('Assessment #42');
  expect(screen.getByText('DRAFT — NOT SUBMITTED')).toBeTruthy();
  expect(screen.getByText('Simulated demo data')).toBeTruthy();
  expect(screen.getByText('Risk level: medium · Risk score: 40/100')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Seller or pharmacy'), { target: { value: 'Community pharmacy' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save report draft' }));
  await screen.findByText('Draft #5 is ready for review.');
  expect(createReportDraft).toHaveBeenCalledWith(expect.objectContaining({ verification_id: 42, pharmacy_name: 'Community pharmacy', purchase_date: null }), expect.any(Object));
  fireEvent.click(screen.getByRole('button', { name: 'Download draft PDF' }));
  await waitFor(() => expect(downloadReportDraft).toHaveBeenCalledWith(5));
});
