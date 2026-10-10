import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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
        scheduled_at: '2099-10-10T04:00:00Z', local_time: '09:00', status: 'pending',
        dose: '1 tablet', taken_at: null, is_demo: false,
      }] }],
    }],
  };
}

beforeEach(() => {
  localStorage.clear();
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

it('loads card-based doses, edits times, creates the schedule, and marks a dose', async () => {
  renderPage();
  expect(screen.getByRole('status', { name: 'Loading your schedule' })).toBeTruthy();
  expect((await screen.findAllByRole('heading', { name: 'Course medicine' })).length).toBe(2);
  expect(screen.getByText('0 of 1 taken today')).toBeTruthy();
  expect(screen.getByText(/Reminders work only while this page is open/)).toBeTruthy();
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('0');

  fireEvent.change(screen.getByLabelText('Reminder 1'), { target: { value: '10:00' } });
  fireEvent.click(screen.getByRole('button', { name: /Create my schedule/ }));
  expect(regenerateScheduleItem).toHaveBeenCalledWith(9, ['10:00', '21:00'], 'Asia/Karachi');

  fireEvent.click(screen.getByRole('button', { name: 'Taken' }));
  expect(await screen.findByText('Taken')).toBeTruthy();
  expect(updateScheduleDose).toHaveBeenCalledWith(31, 'taken');
});

it('shows an overdue nudge without changing the stored status', async () => {
  const data = scheduleData();
  data.items[0].days[0].doses[0].scheduled_at = new Date(Date.now() - (3 * 60 * 60 * 1000)).toISOString();
  getPrescriptionSchedule.mockResolvedValue(data);
  renderPage();

  expect((await screen.findAllByRole('heading', { name: 'Course medicine' })).length).toBe(2);
  expect(screen.getByText('Overdue')).toBeTruthy();
  expect(screen.getByText(/more than 2 hours late/)).toBeTruthy();
  expect(updateScheduleDose).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Skip dose for Course medicine' }));
  expect(updateScheduleDose).toHaveBeenCalledWith(31, 'missed');
  expect(await screen.findByText('Missed')).toBeTruthy();
});

it('leaves new reminder slots empty until the user chooses times', async () => {
  const data = scheduleData();
  data.items[0].status = 'needs_times';
  data.items[0].times = [];
  data.items[0].days = [];
  getPrescriptionSchedule.mockResolvedValue(data);
  renderPage();

  expect(await screen.findByRole('heading', { name: 'Course medicine' })).toBeTruthy();
  expect(screen.getByLabelText('Reminder 1').value).toBe('');
  expect(screen.getByLabelText('Reminder 2').value).toBe('');
  expect(screen.getByRole('button', { name: /Create my schedule/ }).disabled).toBe(true);
});

it('shows a retryable error', async () => {
  getPrescriptionSchedule.mockRejectedValueOnce(new Error('Connection failed')).mockResolvedValueOnce(scheduleData());
  renderPage();
  expect((await screen.findByRole('alert')).textContent).toContain('Connection failed');
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect((await screen.findAllByRole('heading', { name: 'Course medicine' })).length).toBe(2);
});

it('shows the prescription reader action when no confirmed prescription exists', async () => {
  getPrescriptionSchedule.mockResolvedValue({
    prescription_id: null, timezone: 'Asia/Karachi', prescriptions: [], items: [],
  });
  renderPage();
  expect(await screen.findByRole('heading', { name: 'No schedule yet' })).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Go to Prescription Reader' }).getAttribute('href')).toBe('/prescription');
});
