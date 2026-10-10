import { useState } from 'react';
import { ChevronDown, Clock3 } from 'lucide-react';
import Card from '../common/Card';

const routineFields = [
  ['wakeUp', 'Wake up'],
  ['breakfast', 'Breakfast'],
  ['lunch', 'Lunch'],
  ['dinner', 'Dinner'],
  ['bedtime', 'Bedtime'],
];

export default function RoutineCard({ routine, onChange, onSkip }) {
  const [open, setOpen] = useState(false);

  return (
    <Card
      title="Your daily routine"
      titleId="routine-title"
      icon={Clock3}
      footer={(
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button type="button" onClick={onSkip} className="min-h-11 rounded-xl px-3 text-sm font-semibold text-slate-600 underline-offset-4 hover:underline">Skip</button>
          <button type="button" onClick={() => setOpen((value) => !value)} className="button-secondary gap-2" aria-expanded={open} aria-controls="routine-fields">
            {open ? 'Hide routine' : 'Add routine times'} <ChevronDown size={18} className={open ? 'rotate-180' : ''} aria-hidden="true" />
          </button>
        </div>
      )}
    >
      <p className="text-sm leading-6 text-slate-600">Optional routine times make the quick-pick buttons useful. Nothing is filled automatically.</p>
      {open && (
        <div id="routine-fields" className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {routineFields.map(([key, label]) => (
            <label key={key} className="text-sm font-semibold text-slate-700">
              {label}
              <input type="time" value={routine[key] || ''} onChange={(event) => onChange(key, event.target.value)} className="mt-2 min-h-11 w-full rounded-xl border border-slate-400 bg-white px-3 text-base" />
            </label>
          ))}
        </div>
      )}
    </Card>
  );
}
