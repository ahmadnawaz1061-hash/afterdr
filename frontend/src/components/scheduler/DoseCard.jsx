import { Check, Clock3, Pill, RotateCcw, X } from 'lucide-react';
import Card from '../common/Card';
import ErrorMessage from '../common/ErrorMessage';
import StatusBadge from '../common/StatusBadge';
import { formatTime, statusForDose } from './schedulerUtils';

const stateStyles = {
  pending: 'border-slate-200',
  taken: 'border-emerald-300 bg-emerald-50/50 opacity-80',
  missed: 'border-rose-300 bg-rose-50/40',
  overdue: 'border-amber-400 bg-amber-50/50',
};

const stateIcons = { pending: Clock3, taken: Check, missed: X, overdue: Clock3 };

export default function DoseCard({ dose, onStatus, error, busy }) {
  const displayStatus = statusForDose(dose);
  const StateIcon = stateIcons[displayStatus];
  const titleId = `dose-${dose.id}`;

  return (
    <Card
      as="article"
      title={dose.medicine_name}
      titleId={titleId}
      icon={Pill}
      status={<StatusBadge status={displayStatus} />}
      className={stateStyles[displayStatus]}
      footer={(
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          <button type="button" disabled={busy || dose.status === 'taken'} onClick={() => onStatus(dose, 'taken')} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-teal-800 px-5 text-sm font-bold text-white hover:bg-teal-900 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600"><Check size={18} aria-hidden="true" />Taken</button>
          <button type="button" aria-label={`Skip dose for ${dose.medicine_name}`} disabled={busy || dose.status === 'missed'} onClick={() => onStatus(dose, 'missed')} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-rose-300 bg-white px-5 text-sm font-bold text-rose-800 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"><X size={18} aria-hidden="true" />Skip</button>
          {dose.status !== 'pending' && <button type="button" disabled={busy} onClick={() => onStatus(dose, 'pending')} className="col-span-2 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold text-slate-600 hover:bg-slate-100"><RotateCcw size={16} aria-hidden="true" />Undo</button>}
        </div>
      )}
    >
      <div className="grid grid-cols-[auto_1fr] items-start gap-4">
        <time className="text-2xl font-black tracking-tight text-slate-950" dateTime={dose.local_time}>{formatTime(dose.local_time)}</time>
        <div className="min-w-0 border-l border-slate-200 pl-4">
          <p className="text-sm font-semibold text-slate-700">{dose.strength || 'Strength not provided'}</p>
          <p className="mt-1 text-sm text-slate-600">{dose.dose || 'Follow the reviewed dose'} · {dose.instructions || 'Follow reviewed instructions'}</p>
        </div>
      </div>
      {displayStatus === 'overdue' && <p className="mt-4 flex items-start gap-2 rounded-xl bg-amber-100 px-3 py-2.5 text-sm font-semibold text-amber-950"><StateIcon size={18} className="mt-0.5 shrink-0" aria-hidden="true" />This dose is more than 2 hours late. Please record what happened.</p>}
      {error && <div className="mt-4"><ErrorMessage title="Could not update this dose" message={error} /></div>}
    </Card>
  );
}
