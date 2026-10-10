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
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Karachi', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date());
  const value = new Date(`${today}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + offset);
  return value.toISOString().slice(0, 10);
}

export function statusForDose(dose, now = Date.now()) {
  if (dose.status !== 'pending') return dose.status;
  return now - new Date(dose.scheduled_at).getTime() > 2 * 60 * 60 * 1000 ? 'overdue' : 'pending';
}
