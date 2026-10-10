import { useId } from 'react';
import StatusBadge, { DemoBadge } from '../common/StatusBadge';
import { displayValue, medicineDetails, substitutionNotice } from './medicineDetails';

export default function MedicineTable({ medicines = [], caption = 'Medicines', isDemo = false, isAlternative = false }) {
  const captionId = useId();
  const scrollHelpId = useId();
  const showNotice = isAlternative || medicines.some((medicine) => medicine.is_alternative);

  return (
    <div className="min-w-0 space-y-3">
      {showNotice && <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">{substitutionNotice}</p>}
      {medicines.length === 0 ? <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="font-semibold text-slate-900">{caption}</h3>
        {isDemo && <div className="mt-3"><DemoBadge /></div>}
        <p role="status" aria-live="polite" className="mt-2 text-sm text-slate-600">No medicines to display.</p>
      </div> : <>
        <p id={scrollHelpId} className="text-xs text-slate-500">Scroll horizontally to see all medicine details.</p>
        <div role="region" aria-labelledby={captionId} aria-describedby={scrollHelpId} tabIndex={0}
          className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full min-w-180 text-left text-sm">
            <caption id={captionId} className="p-5 text-left font-semibold text-slate-900">{caption}</caption>
            <thead className="border-y border-slate-200 bg-slate-50 text-slate-600">
              <tr>{['Medicine', 'Strength', 'Dose', 'Frequency', 'Duration', 'Status'].map((heading) => <th key={heading} scope="col" className="px-5 py-3 font-semibold">{heading}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {medicines.map((medicine, index) => <tr key={medicine.id ?? index}>
                <th scope="row" className="max-w-72 px-5 py-4 align-top font-medium text-slate-900 wrap-anywhere">
                  {displayValue(medicine.name)}
                  {(isDemo || medicine.is_demo) && <div className="mt-2"><DemoBadge /></div>}
                  {medicine.instructions && <p className="mt-2 font-normal text-slate-600">{medicine.instructions}</p>}
                  {medicine.needs_review && <p className="mt-2 font-normal text-amber-900">Review these instructions before confirming.</p>}
                </th>
                {medicineDetails(medicine).map(([label, value]) => <td key={label} className="max-w-60 px-5 py-4 align-top text-slate-700 wrap-anywhere">{value}</td>)}
                <td className="px-5 py-4 align-top">{medicine.status ? <StatusBadge status={medicine.status} /> : <span className="text-slate-500">Not provided</span>}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
      </>}
    </div>
  );
}
