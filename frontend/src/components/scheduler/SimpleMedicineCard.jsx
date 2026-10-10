import { AlarmClock, BellOff, BellRing, Check, Clock3, Pill, Repeat2, X } from 'lucide-react';
import Card from '../common/Card';
import ErrorMessage from '../common/ErrorMessage';
import StatusBadge from '../common/StatusBadge';
import { statusForDose } from './schedulerUtils';

const rowClass = 'grid grid-cols-[2.5rem_5.5rem_1fr] items-center gap-2 border-b border-slate-100 py-3 last:border-b-0';

export default function SimpleMedicineCard({ item, times, dose, busy, saving, error, onTimeChange, onSaveTimes, onStatus }) {
  const reminderEnabled = item.status === 'scheduled' && item.times.length > 0;
  const displayStatus = dose ? statusForDose(dose) : 'pending';
  const titleId = `medicine-${item.prescription_item_id}`;
  const border = displayStatus === 'taken' ? 'border-emerald-300' : displayStatus === 'missed' ? 'border-rose-300' : displayStatus === 'overdue' ? 'border-amber-400' : 'border-slate-200';

  return (
    <Card
      as="article"
      title={item.medicine_name}
      titleId={titleId}
      icon={Pill}
      className={border}
      footer={(
        <div className="grid grid-cols-2 gap-2">
          <button type="button" disabled={!dose || busy || dose.status === 'taken'} onClick={() => onStatus(dose, 'taken')} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-teal-800 px-4 text-sm font-bold text-white hover:bg-teal-900 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600"><Check size={18} aria-hidden="true" />Taken</button>
          <button type="button" disabled={!dose || busy || dose.status === 'missed'} onClick={() => onStatus(dose, 'missed')} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-rose-300 bg-white px-4 text-sm font-bold text-rose-800 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"><X size={18} aria-hidden="true" />Missed</button>
        </div>
      )}
    >
      <dl>
        <div className={rowClass}>
          {reminderEnabled ? <BellRing size={20} className="text-teal-700" aria-hidden="true" /> : <BellOff size={20} className="text-slate-500" aria-hidden="true" />}
          <dt className="text-sm font-bold text-slate-700">Reminder</dt>
          <dd className="text-sm font-semibold text-slate-900">{reminderEnabled ? 'Enabled' : 'Not enabled'}</dd>
        </div>
        <div className={rowClass}>
          <AlarmClock size={20} className="text-slate-600" aria-hidden="true" />
          <dt className="text-sm font-bold text-slate-700">Status</dt>
          <dd><StatusBadge status={displayStatus} /></dd>
        </div>
        <div className={rowClass}>
          <Pill size={20} className="text-slate-600" aria-hidden="true" />
          <dt className="text-sm font-bold text-slate-700">Dosage</dt>
          <dd className="text-sm font-semibold text-slate-900">{item.dose || 'Not provided'}</dd>
        </div>
        <div className={rowClass}>
          <Repeat2 size={20} className="text-slate-600" aria-hidden="true" />
          <dt className="text-sm font-bold text-slate-700">Frequency</dt>
          <dd className="text-sm font-semibold text-slate-900">{item.frequency || 'Needs review'}</dd>
        </div>
        <div className="grid grid-cols-[2.5rem_1fr] items-start gap-2 py-3">
          <Clock3 size={20} className="mt-3 text-slate-600" aria-hidden="true" />
          <div>
            <dt className="text-sm font-bold text-slate-700">Time</dt>
            <dd className="mt-2 space-y-2">
              {times.map((value, index) => (
                <label key={index} className="block text-xs font-semibold text-slate-600">Reminder {index + 1}
                  <input type="time" value={value} onChange={(event) => onTimeChange(index, event.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-400 bg-white px-3 text-base font-semibold text-slate-950" />
                </label>
              ))}
              <button type="button" disabled={saving || !times.length || times.some((value) => !value)} onClick={onSaveTimes} className="button-secondary w-full disabled:cursor-not-allowed disabled:opacity-50">{saving ? 'Saving…' : reminderEnabled ? 'Save time' : 'Enable reminder'}</button>
            </dd>
          </div>
        </div>
      </dl>
      {displayStatus === 'overdue' && <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-950">This dose is more than 2 hours late. Mark it Taken or Missed.</p>}
      {error && <div className="mt-3"><ErrorMessage title="Could not update this medicine" message={error} /></div>}
    </Card>
  );
}
