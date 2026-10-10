import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { demoCatalog, demoPrescription } from '../mocks/demoData';

const client = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('axios', () => ({ default: { create: vi.fn(() => client) } }));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  client.get.mockReset();
  client.post.mockReset();
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-10T06:00:00Z'));
  vi.stubEnv('VITE_USE_MOCKS', 'false');
  vi.stubEnv('VITE_API_BASE_URL', '');
});

afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs(); });

describe('mock API', () => {
  it.each([
    ['extractPrescription', undefined],
    ['getTodaySchedule', undefined],
    ['searchMedicine', ''],
  ])('%s resolves after 600 ms without making HTTP calls', async (name, argument) => {
    vi.stubEnv('VITE_USE_MOCKS', 'true');
    const api = await import('./api');
    expect(api.USE_MOCKS).toBe(true);
    const resolved = vi.fn();
    const pending = api[name](argument);
    pending.then(resolved);
    await vi.advanceTimersByTimeAsync(599);
    expect(resolved).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(resolved).toHaveBeenCalledOnce();
    const result = await pending;
    if (name === 'extractPrescription') {
      expect(result).toEqual(demoPrescription);
      expect(result.medicines).toHaveLength(2);
      expect(result).not.toHaveProperty('prescription_id');
      expect(result.is_demo).toBe(true);
    } else {
      expect(result).toHaveLength(3);
      expect(result.every((record) => record.is_demo)).toBe(true);
    }
    expect(client.get).not.toHaveBeenCalled();
    expect(client.post).not.toHaveBeenCalled();
  });

  it('returns independent nested copies that cannot corrupt subsequent extraction results', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true');
    const { extractPrescription } = await import('./api');
    const first = extractPrescription();
    await vi.advanceTimersByTimeAsync(600);
    (await first).medicines[0].name = 'Edited by user';
    const second = extractPrescription();
    await vi.advanceTimersByTimeAsync(600);
    expect(await second).toEqual(demoPrescription);
  });

  it.each([
    ['  DEMO MEDICINE A  ', [1]],
    ['ingredient a', [1, 2]],
    ['no matching product', []],
    ['', [1, 2, 3]],
    [undefined, [1, 2, 3]],
  ])('filters medicine search for %s', async (query, ids) => {
    vi.stubEnv('VITE_USE_MOCKS', 'true');
    const { searchMedicine } = await import('./api');
    const result = searchMedicine(query);
    await vi.advanceTimersByTimeAsync(600);
    expect((await result).map(({ id }) => id)).toEqual(ids);
  });

  it('computes today in Asia/Karachi on every call, including across midnight', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true');
    const { getTodaySchedule } = await import('./api');
    const first = getTodaySchedule();
    await vi.advanceTimersByTimeAsync(600);
    expect((await first)[0].scheduled_at).toBe('2026-10-10T04:00:00.000Z');
    vi.setSystemTime(new Date('2026-10-10T19:30:00Z'));
    const second = getTodaySchedule();
    await vi.advanceTimersByTimeAsync(600);
    expect((await second)[0].scheduled_at).toBe('2026-10-11T04:00:00.000Z');
    expect((await second).map(({ status }) => status)).toEqual(['taken', 'missed', 'pending']);
  });
});

describe('real API contract', () => {
  it('keeps the architecture defaults and exports the configured axios instance', async () => {
    const { default: axios } = await import('axios');
    const { default: api, USE_MOCKS } = await import('./api');
    expect(api).toBe(client);
    expect(USE_MOCKS).toBe(false);
    expect(axios.create).toHaveBeenCalledWith({ baseURL: '/api', timeout: 30000, withCredentials: true });
  });

  it('uses the configured API base URL and requires an explicit true mock flag', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'TRUE');
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test/api');
    const { default: axios } = await import('axios');
    const { USE_MOCKS } = await import('./api');
    expect(USE_MOCKS).toBe(false);
    expect(axios.create).toHaveBeenCalledWith({ baseURL: 'https://api.example.test/api', timeout: 30000, withCredentials: true });
  });

  it('posts the image under file with the extraction timeout and returns response.data', async () => {
    client.post.mockResolvedValueOnce({ data: demoPrescription });
    const { extractPrescription } = await import('./api');
    const file = new File(['image bytes'], 'prescription.png', { type: 'image/png' });
    expect(await extractPrescription(file)).toBe(demoPrescription);
    const [url, body, options] = client.post.mock.calls[0];
    expect(url).toBe('/prescriptions/extract');
    expect(body.get('file')).toBe(file);
    expect(options).toEqual({ timeout: 60000 });
    expect(vi.getTimerCount()).toBe(0);
  });

  it('uses the schedule and medicine search endpoints without adding response wrappers', async () => {
    const { getTodaySchedule, searchMedicine } = await import('./api');
    client.get.mockResolvedValueOnce({ data: [] }).mockResolvedValueOnce({ data: demoCatalog });
    expect(await getTodaySchedule()).toEqual([]);
    expect(client.get).toHaveBeenNthCalledWith(1, '/schedules/today');
    expect(await searchMedicine('Demo')).toBe(demoCatalog);
    expect(client.get).toHaveBeenNthCalledWith(2, '/medicines/search', { params: { q: 'Demo' } });
  });

  it.each(['extractPrescription', 'getTodaySchedule', 'searchMedicine'])('%s propagates network errors instead of substituting demo results', async (name) => {
    const failure = new Error('Connection failed');
    client.get.mockRejectedValue(failure);
    client.post.mockRejectedValue(failure);
    const api = await import('./api');
    await expect(api[name]()).rejects.toBe(failure);
    expect(vi.getTimerCount()).toBe(0);
  });
});
