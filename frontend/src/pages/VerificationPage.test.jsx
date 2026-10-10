import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import VerificationPage from './VerificationPage';
import * as api from '../services/api';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('VerificationPage — Medicine Authenticity Checker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders step 1 with upload zone and Pakistan DRAP badge', () => {
    render(
      <MemoryRouter>
        <VerificationPage />
      </MemoryRouter>
    );

    expect(screen.getByText('Medicine Authenticity Checker')).toBeInTheDocument();
    expect(screen.getByText('Pakistan DRAP Verified Catalog')).toBeInTheDocument();
    expect(screen.getByText(/Step 1 — Upload Medicine Packaging Image/i)).toBeInTheDocument();
    expect(screen.getByText(/Quick Demo Packaging Samples/i)).toBeInTheDocument();
  });

  it('loads sample packaging and transitions to review form', () => {
    render(
      <MemoryRouter>
        <VerificationPage />
      </MemoryRouter>
    );

    const sampleBtn = screen.getByRole('button', { name: /Augmentin 625mg \(DRAP Reg #012345\)/i });
    fireEvent.click(sampleBtn);

    expect(screen.getByText(/Step 2 — Review & Confirm Extracted Packaging Fields/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue('Augmentin')).toBeInTheDocument();
    expect(screen.getByDisplayValue('GlaxoSmithKline Pakistan Limited')).toBeInTheDocument();
    expect(screen.getByDisplayValue('012345')).toBeInTheDocument();
  });

  it('submits verification and displays authenticity assessment results', async () => {
    vi.spyOn(api, 'verifyPackage').mockResolvedValueOnce({
      verification_id: 501,
      status: 'inconsistent_information',
      findings: [
        { field: 'manufacturer', result: 'mismatch', message: 'Manufacturer differs from demo reference entry' },
      ],
      counterfeit_confirmed: false,
      source: 'DRAP Rapid Alert / Safety Notice',
      limitations: 'A record match does not prove that a physical package is authentic.',
      is_demo: true,
      outcome: 'possible_recall',
      outcome_label: 'Possible recall or safety alert',
      summary_message: 'This product or batch matches an official DRAP Rapid Alert.',
      discrepancies: ['CRITICAL RECALL ALERT (DRAP-RAS-2024-001): Falsified product detected.'],
      evidence: [
        {
          category: 'safety_recall',
          source: 'DRAP Rapid Alert System',
          detail: 'Class 1 Falsified product notice.',
          is_critical: true,
          source_url: 'https://www.dra.gov.pk/safety-alerts/ras-2024-001/',
        },
      ],
      recommended_next_steps: [
        'Do NOT consume or administer this medicine under any circumstances.',
        'Quarantine the medicine in a secure location.',
      ],
      source_links: [{ title: 'Drug Regulatory Authority of Pakistan (DRAP)', url: 'https://www.dra.gov.pk/' }],
    });

    render(
      <MemoryRouter>
        <VerificationPage />
      </MemoryRouter>
    );

    // Load sample
    fireEvent.click(screen.getByRole('button', { name: /DRAP Recalled Batch/i }));

    // Submit verification
    const submitBtn = screen.getByRole('button', { name: /Verify Packaging Authenticity/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Possible recall or safety alert')).toBeInTheDocument();
    });

    expect(screen.getByText(/Verification ID #501/i)).toBeInTheDocument();
    expect(screen.getByText(/Essential Safety & Authenticity Limitation Notice/i)).toBeInTheDocument();
    expect(screen.getByText(/CRITICAL RECALL ALERT/i)).toBeInTheDocument();
    expect(screen.getByText(/Do NOT consume or administer this medicine/i)).toBeInTheDocument();
    expect(screen.getByText(/Prepare DRAP Complaint Draft/i)).toBeInTheDocument();
  });

  it('navigates to complaint reporting with verification ID when clicking draft button', async () => {
    vi.spyOn(api, 'verifyPackage').mockResolvedValueOnce({
      verification_id: 99,
      status: 'inconsistent_information',
      findings: [],
      counterfeit_confirmed: false,
      source: 'demo_dataset',
      limitations: 'Physical package authenticity unconfirmed.',
      is_demo: true,
      outcome: 'potentially_suspicious',
      outcome_label: 'Potentially suspicious',
      summary_message: 'Mismatched packaging details.',
      discrepancies: ['Manufacturer mismatch'],
      evidence: [],
      recommended_next_steps: ['Prepare DRAP complaint draft'],
      source_links: [],
    });

    render(
      <MemoryRouter>
        <VerificationPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: /Suspicious Mismatched Manufacturer/i }));
    fireEvent.click(screen.getByRole('button', { name: /Verify Packaging Authenticity/i }));

    await waitFor(() => {
      expect(screen.getByText('Potentially suspicious')).toBeInTheDocument();
    });

    const reportBtn = screen.getByRole('button', { name: /Prepare DRAP Complaint Draft/i });
    fireEvent.click(reportBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/reporting?verification_id=99');
  });

  it('allows adding visual anomaly flags in review form', () => {
    render(
      <MemoryRouter>
        <VerificationPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: /Augmentin 625mg/i }));

    const reportVisualBtn = screen.getByRole('button', { name: /\+ Report Visual Issue/i });
    fireEvent.click(reportVisualBtn);

    const anomalyInput = screen.getByPlaceholderText(/Misaligned font, missing security hologram/i);
    fireEvent.change(anomalyInput, { target: { value: 'Tamper seal broken' } });

    fireEvent.click(screen.getByRole('button', { name: 'Add Anomaly' }));
    expect(screen.getByText('Tamper seal broken')).toBeInTheDocument();
  });
});
