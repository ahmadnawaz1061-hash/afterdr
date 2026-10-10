import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SchedulerPage from './SchedulerPage';
import { getPrescriptionSchedule, regenerateScheduleItem, updateScheduleDose } from '../services/api';

vi.mock('../services/api', () => ({
  USE_MOCKS: false,
  getPrescriptionSchedule: vi.fn(),
  regenerateScheduleItem: vi.fn(),
  updateScheduleDose: vi.fn(),
}));

const today = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Karachi', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());

function scheduleData() {
  return {
    prescription_id: 4,
    timezone: 'Asia/Karachi',
    prescriptions: [{ prescription_id: 4, created_at: '2026-10-10T00:00:00Z' }],
    items: [{
      prescription_item_id: 9,
      medicine_name: 'Course medicine',
      dose: '1 tablet',
      frequency: 'twice daily',
      duration_days: 5,
      status: 'scheduled',
      reason: null,
      times: ['09:00', '21:00'],
      suggested_times: ['09:00', '21:00'],
      course_start: today,
      course_end: today,
      days: [{ date: today, doses: [{
        id: 31, prescription_item_id: 9, medicine_name: 'Course medicine',
        scheduled_at: `${today}T04:00:00Z`, local_time: '09:00', status: 'pending',
        taken_at: null, is_demo: false,
      }] }],
    }],
  };
}

beforeEach(() => {
  getPrescriptionSchedule.mockReset().mockResolvedValue(scheduleData());
  regenerateScheduleItem.mockReset().mockResolvedValue({ schedule_id: 9, doses_created: 10, status: 'scheduled' });
  updateScheduleDose.mockReset().mockImplementation((id, status) => Promise.resolve({
    ...scheduleData().items[0].days[0].doses[0], id, status,
  }));
});
afterEach(cleanup);

function renderPage() {
  return render(<MemoryRouter initialEntries={['/scheduler?prescription_id=4']}><SchedulerPage /></MemoryRouter>);
}

it('loads generated doses, edits times, and marks a dose', async () => {
  renderPage();
  expect(screen.getByText('Loading your schedule…')).toBeTruthy();
  expect(await screen.findByRole('heading', { name: 'Course medicine' })).toBeTruthy();
  expect(screen.getByText(/Schedule created automatically/)).toBeTruthy();
  expect(screen.getByText(/Reminders work inside this app only/)).toBeTruthy();
  const summary = screen.getByRole('region', { name: 'Today’s dose summary' });
  expect(within(summary).getByText('total').previousSibling.textContent).toBe('1');

  fireEvent.change(screen.getByLabelText('Reminder time 1 for Course medicine'), { target: { value: '10:00' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save new times' }));
  expect(regenerateScheduleItem).toHaveBeenCalledWith(9, ['10:00', '21:00'], 'Asia/Karachi');

  fireEvent.click(screen.getByRole('button', { name: 'taken' }));
  expect(await screen.findByText('Taken')).toBeTruthy();
  expect(updateScheduleDose).toHaveBeenCalledWith(31, 'taken');
});

it('shows a retryable error', async () => {
  getPrescriptionSchedule.mockRejectedValueOnce(new Error('Connection failed')).mockResolvedValueOnce(scheduleData());
  renderPage();
  expect((await screen.findByRole('alert')).textContent).toContain('Connection failed');
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByRole('heading', { name: 'Course medicine' })).toBeTruthy();
});

it('shows the prescription reader action when no confirmed prescription exists', async () => {
  getPrescriptionSchedule.mockResolvedValue({
    prescription_id: null, timezone: 'Asia/Karachi', prescriptions: [], items: [],
  });
  renderPage();
  expect(await screen.findByRole('heading', { name: 'No confirmed prescription yet' })).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Go to Prescription Reader' }).getAttribute('href')).toBe('/prescription');
});
