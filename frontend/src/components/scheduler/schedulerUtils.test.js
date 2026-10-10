import { afterEach, expect, it, vi } from 'vitest';
import { dateAtOffset } from './schedulerUtils';

afterEach(() => vi.useRealTimers());

it.each([
  ['2026-10-10T18:59:59Z', 0, '2026-10-10'],
  ['2026-10-10T19:00:00Z', 0, '2026-10-11'],
  ['2026-10-10T19:00:00Z', -1, '2026-10-10'],
  ['2026-12-31T19:00:00Z', 1, '2027-01-02'],
  ['2028-02-28T19:00:00Z', 1, '2028-03-01'],
])('uses the Karachi calendar at %s with offset %i', (instant, offset, expected) => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(instant));
  expect(dateAtOffset(offset)).toBe(expected);
});
