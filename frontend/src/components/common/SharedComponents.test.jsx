import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import LoadingState from './LoadingState';
import ErrorMessage from './ErrorMessage';
import StatusBadge from './StatusBadge';
import MedicineCard from '../medicine/MedicineCard';
import MedicineTable from '../medicine/MedicineTable';
import { demoMedicines } from '../../mocks/demoData';

afterEach(cleanup);

it('announces loading and custom errors, with an optional retry action', () => {
  const { rerender } = render(<LoadingState title="Reading prescription…" message="Review will follow." />);
  expect(screen.getByRole('status').textContent).toContain('Reading prescription…');
  expect(screen.getByRole('status').getAttribute('aria-live')).toBe('polite');
  rerender(<ErrorMessage message="Image could not be read." />);
  expect(screen.getByRole('alert').textContent).toContain('Image could not be read.');
  expect(screen.queryByRole('button')).toBeNull();
  const retry = vi.fn();
  rerender(<ErrorMessage onRetry={retry} retryLabel="Read again" />);
  fireEvent.click(screen.getByRole('button', { name: 'Read again' }));
  expect(retry).toHaveBeenCalledOnce();
});

it('surfaces string and validation-list detail messages from FastAPI errors', () => {
  const { rerender } = render(<ErrorMessage error={{ response: { data: { detail: 'Image format is not supported.' } } }} message="Fallback" />);
  expect(screen.getByRole('alert').textContent).toContain('Image format is not supported.');
  expect(screen.queryByText('Fallback')).toBeNull();
  rerender(<ErrorMessage error={{ response: { data: { detail: [{ msg: 'Field is required' }, { msg: 'Value is invalid' }] } } }} />);
  expect(screen.getByRole('alert').textContent).toContain('Field is required Value is invalid');
});

it.each([
  ['pending', 'Pending'], ['taken', 'Taken'], ['missed', 'Missed'],
  ['record_match', 'Record match found'],
  ['inconsistent_information', 'Potential inconsistency'],
  ['unable_to_verify', 'Unable to verify'],
  ['unknown', 'Unable to verify'],
])('displays the permitted label for %s', (status, label) => {
  render(<StatusBadge status={status} />);
  expect(screen.getByText(label)).toBeTruthy();
});

it('shows a labelled medicine card with demo provenance, review notice, and alternative warning', () => {
  render(<MedicineCard medicine={demoMedicines[0]} isAlternative />);
  expect(screen.getByRole('article', { name: demoMedicines[0].name })).toBeTruthy();
  expect(screen.getByText('Simulated demo data')).toBeTruthy();
  expect(screen.getByText('Pending')).toBeTruthy();
  expect(screen.getByText('Review these instructions before confirming.')).toBeTruthy();
  expect(screen.getByText('Confirm with your pharmacist or prescriber before substituting.')).toBeTruthy();
  expect(screen.getByText('5 days')).toBeTruthy();
});

it('does not infer instructions for incomplete medicine records', () => {
  render(<MedicineCard medicine={{ name: demoMedicines[0].name }} />);
  expect(screen.getAllByText('Not provided')).toHaveLength(4);
  expect(screen.queryByText('Pending')).toBeNull();
  expect(screen.queryByText('Simulated demo data')).toBeNull();
});

it('provides table semantics, row demo labels, and a keyboard-accessible scroll region', () => {
  render(<MedicineTable medicines={demoMedicines} isAlternative caption="Prescription medicines" />);
  expect(screen.getByRole('table', { name: 'Prescription medicines' })).toBeTruthy();
  expect(screen.getByRole('region', { name: 'Prescription medicines' }).tabIndex).toBe(0);
  expect(screen.getAllByRole('columnheader')).toHaveLength(6);
  expect(screen.getByRole('rowheader').textContent).toContain(demoMedicines[0].name);
  expect(screen.getByText('Simulated demo data')).toBeTruthy();
  expect(screen.getByText('Confirm with your pharmacist or prescriber before substituting.')).toBeTruthy();
});

it.each([MedicineCard, MedicineTable])('retains demo and substitution notices with empty data', (Component) => {
  render(<Component isDemo isAlternative />);
  expect(screen.getByRole('status').textContent).toMatch(/No medicine/);
  expect(screen.getByText('Simulated demo data')).toBeTruthy();
  expect(screen.getByText('Confirm with your pharmacist or prescriber before substituting.')).toBeTruthy();
});

it('recognizes alternative records without requiring a table-level flag', () => {
  render(<MedicineTable medicines={[{ ...demoMedicines[0], is_alternative: true }]} />);
  expect(screen.getByText('Confirm with your pharmacist or prescriber before substituting.')).toBeTruthy();
});
