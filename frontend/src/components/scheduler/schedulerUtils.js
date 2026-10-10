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

export function dateAtOffset(offset) {
  const value = new Date();
  value.setHours(12, 0, 0, 0);
  value.setDate(value.getDate() + offset);
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Karachi', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(value);
}

export function statusForDose(dose, now = Date.now()) {
  if (dose.status !== 'pending') return dose.status;
  return now - new Date(dose.scheduled_at).getTime() > 2 * 60 * 60 * 1000 ? 'overdue' : 'pending';
}
