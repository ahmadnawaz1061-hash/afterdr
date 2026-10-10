import { expect, it } from 'vitest';
import { demoAlternatives, demoCatalog, demoPackageExtraction, demoPrescription, demoVerificationResult } from './demoData';

it('keeps extraction unconfirmed, without saved identifiers or inferred missing instructions', () => {
  expect(demoPrescription.status).toBe('needs_review');
  expect(demoPrescription.medicines).toHaveLength(2);
  expect(demoPrescription.medicines.every((item) => item.is_demo && item.needs_review)).toBe(true);
  for (const item of demoPrescription.medicines) expect(item).not.toHaveProperty('id');
  expect(demoPrescription.medicines[1].instructions).toBeNull();
});

it('links alternatives only to catalog candidates with all documented attributes matching', () => {
  expect(demoCatalog).toHaveLength(3);
  for (const medicine of demoCatalog) {
    expect(medicine.is_demo).toBe(true);
    expect(medicine.data_source).toBe('demo_dataset');
    expect(medicine.registration_no).toBeNull();
    expect(demoAlternatives[medicine.id]).toBeInstanceOf(Array);
    for (const candidate of demoAlternatives[medicine.id]) {
      expect(candidate.id).not.toBe(medicine.id);
      expect(demoCatalog.some(({ id }) => id === candidate.id)).toBe(true);
      expect(candidate.is_alternative).toBe(true);
      expect(candidate.is_demo).toBe(true);
      expect(candidate.match_reasons).toHaveLength(5);
      expect(candidate.notice).toBe('Confirm with your pharmacist or prescriber before substituting.');
      for (const field of ['active_ingredient', 'strength', 'dosage_form', 'route', 'release_type']) {
        expect(candidate[field]).toBe(medicine[field]);
      }
    }
  }
  expect(demoAlternatives[3]).toEqual([]);
});

it('keeps the package and verification fixtures consistent and explicitly simulated', () => {
  expect(demoPackageExtraction.needs_review).toBe(true);
  expect(demoPackageExtraction.is_demo).toBe(true);
  const reference = demoCatalog.find(({ brand_name }) => brand_name === demoPackageExtraction.brand_name);
  expect(reference.manufacturer).not.toBe(demoPackageExtraction.manufacturer);
  expect(demoVerificationResult.status).toBe('inconsistent_information');
  expect(demoVerificationResult.findings[0].field).toBe('manufacturer');
  expect(demoVerificationResult.counterfeit_confirmed).toBe(false);
  expect(demoVerificationResult.source).toBe('demo_dataset');
  expect(demoVerificationResult.limitations).toContain('does not prove that a physical package is authentic');
  expect(demoVerificationResult.is_demo).toBe(true);
});
