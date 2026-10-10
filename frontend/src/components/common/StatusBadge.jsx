export const verificationStatuses = {
  record_match: 'Record match found',
  inconsistent_information: 'Potential inconsistency',
  unable_to_verify: 'Unable to verify',
};

export const doseStatuses = {
  pending: 'Pending',
  taken: 'Taken',
  missed: 'Missed',
};

const labels = { ...verificationStatuses, ...doseStatuses };

const colors = {
  pending: 'bg-amber-50 text-amber-900 ring-amber-200',
  taken: 'bg-teal-50 text-teal-800 ring-teal-200',
  missed: 'bg-rose-50 text-rose-800 ring-rose-200',
  record_match: 'bg-teal-50 text-teal-800 ring-teal-200',
  inconsistent_information: 'bg-amber-50 text-amber-900 ring-amber-200',
  unable_to_verify: 'bg-slate-100 text-slate-700 ring-slate-200',
};

export function DemoBadge() {
  return <span className="badge bg-violet-50 text-violet-800 ring-violet-200">Simulated demo data</span>;
}

export function DraftBadge() {
  return <span className="badge bg-amber-50 text-amber-900 ring-amber-200">DRAFT — NOT SUBMITTED</span>;
}

export default function StatusBadge({ status }) {
  const value = Object.hasOwn(labels, status) ? status : 'unable_to_verify';
  return <span className={`badge ${colors[value]}`}>{labels[value]}</span>;
}
