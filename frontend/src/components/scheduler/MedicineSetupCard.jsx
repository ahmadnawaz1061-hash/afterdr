import { AlertTriangle, CheckCircle2, Copy, Pill, Plus, Trash2 } from 'lucide-react';
import Card from '../common/Card';
import { dateAtOffset, formatDateRange, formatTime, frequencyLabel, reminderCount, timesTooClose } from './schedulerUtils';

const quickPicks = [
  ['Morning', ['wakeUp', 'breakfast']],
  ['Lunch', ['lunch']],
  ['Dinner', ['dinner']],
  ['Bedtime', ['bedtime']],
];

function SetupStatus({ ready, skipped }) {
  if (skipped) return <span className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs font-bold text-slate-700"><CheckCircle2 size={15} aria-hidden="true" />Skipped</span>;
  if (ready) return <span className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-50 px-2.5 py-1.5 text-xs font-bold text-emerald-800 ring-1 ring-emerald-200"><CheckCircle2 size={15} aria-hidden="true" />Ready</span>;
  return <span className="inline-flex items-center gap-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs font-bold text-amber-900 ring-1 ring-amber-200"><AlertTriangle size={15} aria-hidden="true" />Needs attention</span>;
}

export default function MedicineSetupCard({ item, setup, routine, onChange, onCopy, onSkip }) {
  const expectedCount = reminderCount(item.frequency);
  const selectedTimes = setup.times.filter(Boolean);
  const ready = expectedCount > 0
    && selectedTimes.length === expectedCount
    && Boolean(setup.startDate)
    && Number(setup.durationDays) > 0;
  const closeTimes = timesTooClose(selectedTimes);
  const cardState = setup.skipped
    ? 'border-slate-300'
    : ready
      ? 'border-emerald-400 ring-1 ring-emerald-100'
      : 'border-amber-300 ring-1 ring-amber-100';
  const titleId = `medicine-setup-${item.prescription_item_id}`;

  function fillQuickPick(keys) {
    const value = keys.map((key) => routine[key]).find(Boolean);
    if (!value) return;
    const emptyIndex = setup.times.findIndex((time) => !time);
    if (emptyIndex >= 0) {
      onChange({ times: setup.times.map((time, index) => index === emptyIndex ? value : time), skipped: false });
    }
  }

  function removeTime(index) {
    onChange({ times: setup.times.filter((_, timeIndex) => timeIndex !== index), skipped: false });
  }

  return (
    <Card
      as="article"
      title={item.medicine_name}
      titleId={titleId}
      icon={Pill}
      status={<SetupStatus ready={ready} skipped={setup.skipped} />}
      className={cardState}
      footer={(
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
          <button type="button" onClick={() => onCopy(item.prescription_item_id)} disabled={!selectedTimes.length} className="button-secondary gap-2 disabled:cursor-not-allowed disabled:opacity-50"><Copy size={17} aria-hidden="true" />Copy times to other medicines</button>
          <button type="button" onClick={() => onSkip(item.prescription_item_id)} className="min-h-11 rounded-xl px-4 text-sm font-semibold text-slate-600 hover:bg-slate-100">{setup.skipped ? 'Include medicine' : 'Skip for now'}</button>
        </div>
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="badge bg-slate-100 text-slate-700 ring-slate-200">{frequencyLabel(item.frequency, setup.durationDays)}</span>
        <span className="text-sm font-medium text-slate-600">{item.strength || 'Strength not provided'}</span>
      </div>
      <p className="mt-3 text-base text-slate-800">Take {item.dose || 'the prescribed dose'}{item.instructions ? `, ${item.instructions.toLowerCase()}` : ' as reviewed'}.</p>

      {setup.skipped ? (
        <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">This medicine will be left out when you create the schedule.</p>
      ) : (
        <>
          <h3 className="mt-5 font-bold text-slate-950">{expectedCount ? `When would you like your ${expectedCount} reminder${expectedCount === 1 ? '' : 's'}?` : 'When would you like your reminders?'}</h3>
          {!expectedCount && <p className="mt-2 text-sm font-medium text-amber-900">The frequency needs review. Add reminder slots only when you know the reviewed instructions.</p>}
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {setup.times.map((value, index) => (
              <div key={`${item.prescription_item_id}-${index}`} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <label htmlFor={`time-${item.prescription_item_id}-${index}`} className="text-sm font-bold text-slate-700">Reminder {index + 1}</label>
                  <button type="button" onClick={() => removeTime(index)} className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-rose-700 hover:bg-rose-50" aria-label={`Remove reminder ${index + 1} for ${item.medicine_name}`}><Trash2 size={18} aria-hidden="true" /></button>
                </div>
                <input id={`time-${item.prescription_item_id}-${index}`} type="time" value={value} onChange={(event) => onChange({ times: setup.times.map((time, timeIndex) => timeIndex === index ? event.target.value : time), skipped: false })} className="mt-2 min-h-14 w-full rounded-xl border border-slate-400 bg-white px-4 text-xl font-bold text-slate-950" />
              </div>
            ))}
          </div>
          {setup.times.length < (expectedCount || 4) && <button type="button" onClick={() => onChange({ times: [...setup.times, ''], skipped: false })} className="button-secondary mt-3 gap-2"><Plus size={17} aria-hidden="true" />Add reminder</button>}

          <div className="mt-5">
            <p className="text-sm font-bold text-slate-800">Quick picks from your routine</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {quickPicks.map(([label, keys]) => {
                const value = keys.map((key) => routine[key]).find(Boolean);
                return <button key={label} type="button" disabled={!value} onClick={() => fillQuickPick(keys)} className="min-h-11 rounded-full border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 hover:border-teal-700 hover:bg-teal-50 disabled:cursor-not-allowed disabled:opacity-45">{label}{value ? ` · ${formatTime(value)}` : ''}</button>;
              })}
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <fieldset>
              <legend className="text-sm font-bold text-slate-800">Start date</legend>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <button type="button" onClick={() => onChange({ startDate: dateAtOffset(0) })} aria-pressed={setup.startDate === dateAtOffset(0)} className="min-h-11 rounded-xl border border-slate-300 px-3 text-sm font-semibold aria-pressed:border-teal-700 aria-pressed:bg-teal-50 aria-pressed:text-teal-900">Today</button>
                <button type="button" onClick={() => onChange({ startDate: dateAtOffset(1) })} aria-pressed={setup.startDate === dateAtOffset(1)} className="min-h-11 rounded-xl border border-slate-300 px-3 text-sm font-semibold aria-pressed:border-teal-700 aria-pressed:bg-teal-50 aria-pressed:text-teal-900">Tomorrow</button>
              </div>
            </fieldset>
            <label className="text-sm font-bold text-slate-800">Duration (days)
              <input type="number" min="1" max="365" value={setup.durationDays} onChange={(event) => onChange({ durationDays: event.target.value })} className="mt-2 min-h-11 w-full rounded-xl border border-slate-400 bg-white px-3 text-base" />
            </label>
          </div>

          <div className="mt-5 rounded-xl bg-teal-50 p-4 text-sm text-teal-950" aria-live="polite">
            <p className="font-bold">{selectedTimes.length && setup.durationDays ? `${selectedTimes.length * Number(setup.durationDays)} reminders: ${selectedTimes.map(formatTime).join(' and ')}, ${formatDateRange(setup.startDate, setup.durationDays)}.` : 'Choose all reminder times to see your schedule preview.'}</p>
            {closeTimes && <p className="mt-2 flex items-start gap-2 font-semibold text-amber-900"><AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />Some times are under 2 hours apart. Check that they match your reviewed instructions.</p>}
          </div>
        </>
      )}
    </Card>
  );
}
