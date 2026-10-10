import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import catalog from '../../../backend/data/alternative_medicines_pk.json';
import { getMedicineAlternatives, searchAlternativeMedicines } from './alternativesApi';

const client = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('./api', () => ({ default: client }));
const medicine = { id: 1, ...catalog.records[0], is_demo: false };
beforeEach(() => { client.get.mockReset(); vi.stubEnv('VITE_USE_MOCKS', 'true'); });
afterEach(() => vi.unstubAllEnvs());

it('uses real Pakistan HTTP search even if other modules use mock mode', async () => {
  client.get.mockResolvedValue({ data: [medicine] });
  const controller = new AbortController();
  expect(await searchAlternativeMedicines('  Panadol  ', { signal: controller.signal })).toEqual([medicine]);
  expect(client.get).toHaveBeenCalledWith('/medicines/search', { params: { q: 'Panadol', catalog: 'drap_pk' }, signal: controller.signal });
});

it('uses the existing alternatives endpoint with a Pakistan-only filter', async () => {
  const candidate = { id: 2, ...catalog.records[1], is_alternative: true, match_reasons: ['Same active ingredient(s)'] };
  client.get.mockResolvedValue({ data: [candidate] });
  expect(await getMedicineAlternatives(1)).toEqual([candidate]);
  expect(client.get).toHaveBeenCalledWith('/medicines/1/alternatives', { params: { catalog: 'drap_pk' }, signal: undefined });
});

it('preserves empty results without adding fictional records', async () => {
  client.get.mockResolvedValue({ data: [] });
  expect(await searchAlternativeMedicines()).toEqual([]);
  expect(await getMedicineAlternatives(1)).toEqual([]);
});

it.each([{}, null, [null], [{ ...medicine, data_source: 'demo_dataset' }], [{ ...medicine, id: -1 }]])('rejects malformed or foreign catalog responses %s', async (data) => {
  client.get.mockResolvedValue({ data });
  await expect(searchAlternativeMedicines('Panadol')).rejects.toThrow('invalid response');
});

it('rejects malformed candidate explanations', async () => {
  client.get.mockResolvedValue({ data: [{ ...medicine, is_alternative: true, match_reasons: [null] }] });
  await expect(getMedicineAlternatives(1)).rejects.toThrow('invalid response');
});

it('propagates errors and cancellation without a demo fallback', async () => {
  const error = new Error('Network unavailable');
  client.get.mockRejectedValue(error);
  await expect(searchAlternativeMedicines('Panadol')).rejects.toBe(error);
  await expect(getMedicineAlternatives(1)).rejects.toBe(error);
});

it.each([0, -1, NaN, 1.2, '1'])('validates medicine ID %s before making requests', async (id) => {
  await expect(getMedicineAlternatives(id)).rejects.toThrow('Select a medicine');
  expect(client.get).not.toHaveBeenCalled();
});

it('validates search length before making requests', async () => {
  await expect(searchAlternativeMedicines('x'.repeat(101))).rejects.toThrow('100 characters');
  expect(client.get).not.toHaveBeenCalled();
});

it('requests the next Pakistan catalog page', async () => {
  client.get.mockResolvedValue({ data: [medicine] });
  await searchAlternativeMedicines('paracetamol', { offset: 10 });
  expect(client.get).toHaveBeenCalledWith('/medicines/search', { params: { q: 'paracetamol', catalog: 'drap_pk', offset: 10 }, signal: undefined });
});

it.each([-1, 0.5, NaN, '10', 10001])('rejects invalid page offset %s before making requests', async (offset) => {
  await expect(searchAlternativeMedicines('', { offset })).rejects.toThrow('Invalid catalog page');
  expect(client.get).not.toHaveBeenCalled();
});
