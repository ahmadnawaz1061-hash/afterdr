const frequencyPatterns = [
  [/four times|qid/i, 4],
  [/three times|tds|tid/i, 3],
  [/twice|two times|bd|bid|every 12 hours/i, 2],
  [/once|daily|od|morning|evening|bedtime|night|hs/i, 1],
];

export function reminderCount(frequency) {
  if (!frequency) return 0;
  return frequencyPatterns.find(([pattern]) => pattern.test(frequency))?.[1] || 0;
}

export function frequencyLabel(frequency, durationDays) {
  const count = reminderCount(frequency);
  const countLabel = count === 1 ? 'Once a day' : count === 2 ? 'Twice a day' : count ? `${count} times a day` : 'Times need review';
  const duration = durationDays ? `${durationDays} day${durationDays === 1 ? '' : 's'}` : 'duration needed';
  return `${countLabel}, ${duration}`;
}

export function formatTime(value) {
  if (!value) return 'Time not set';
  const [hours, minutes] = value.split(':').map(Number);
  const suffix = hours >= 12 ? 'PM' : 'AM';
  const displayHours = hours % 12 || 12;
  return `${displayHours}:${String(minutes).padStart(2, '0')} ${suffix}`;
}

export function dateAtOffset(offset) {
  const value = new Date();
  value.setHours(12, 0, 0, 0);
  value.setDate(value.getDate() + offset);
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Karachi', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(value);
}

export function formatDateRange(startDate, durationDays) {
  if (!startDate || !durationDays) return 'Choose a start date and duration';
  const start = new Date(`${startDate}T12:00:00`);
  const end = new Date(start);
  end.setDate(end.getDate() + Number(durationDays) - 1);
  const formatter = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
  return `${formatter.format(start)} to ${formatter.format(end)}`;
}

export function timesTooClose(times) {
  const minutes = times.filter(Boolean).map((value) => {
    const [hours, mins] = value.split(':').map(Number);
    return hours * 60 + mins;
  }).sort((a, b) => a - b);
  if (minutes.length < 2) return false;
  return minutes.some((value, index) => {
    const next = minutes[(index + 1) % minutes.length] + (index === minutes.length - 1 ? 1440 : 0);
    return next - value < 120;
  });
}

export function statusForDose(dose, now = Date.now()) {
  if (dose.status !== 'pending') return dose.status;
  return now - new Date(dose.scheduled_at).getTime() > 2 * 60 * 60 * 1000 ? 'overdue' : 'pending';
}
