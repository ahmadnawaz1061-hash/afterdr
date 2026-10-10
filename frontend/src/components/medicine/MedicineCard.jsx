import { useId } from 'react';
import { Pill } from 'lucide-react';
import StatusBadge, { DemoBadge } from '../common/StatusBadge';
import { displayValue, medicineDetails, substitutionNotice } from './medicineDetails';

export default function MedicineCard({ medicine, isDemo = false, isAlternative = false }) {
  const titleId = useId();
  if (!medicine) {
    return <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
      {isDemo && <DemoBadge />}
      <p role="status" aria-live="polite" className="mt-2">No medicine selected.</p>
      {isAlternative && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-amber-950">{substitutionNotice}</p>}
    </div>;
  }

  return (
    <article aria-labelledby={titleId} className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <Pill size={22} className="mt-1 shrink-0 text-teal-700" aria-hidden="true" />
        <h3 id={titleId} className="min-w-0 text-lg font-semibold text-slate-900 wrap-anywhere">{displayValue(medicine.name)}</h3>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {(isDemo || medicine.is_demo) && <DemoBadge />}
        {medicine.status && <StatusBadge status={medicine.status} />}
      </div>
      <dl className="mt-5 grid grid-cols-1 gap-4 min-[360px]:grid-cols-2">
        {medicineDetails(medicine).map(([label, value]) => <div key={label} className="min-w-0">
          <dt className="text-xs font-medium text-slate-500">{label}</dt>
          <dd className="mt-1 text-sm text-slate-900 wrap-anywhere">{value}</dd>
        </div>)}
      </dl>
      {medicine.instructions && <p className="mt-4 text-sm text-slate-600 wrap-anywhere"><span className="font-semibold">Instructions: </span>{medicine.instructions}</p>}
      {medicine.needs_review && <p className="mt-4 text-sm font-medium text-amber-900">Review these instructions before confirming.</p>}
      {(isAlternative || medicine.is_alternative) && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-950">{substitutionNotice}</p>}
    </article>
  );
}
