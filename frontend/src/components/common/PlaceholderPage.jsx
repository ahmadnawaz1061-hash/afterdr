import { ArrowRight, Inbox } from 'lucide-react';
import { Link } from 'react-router-dom';
import { DraftBadge } from './StatusBadge';

const emptyMessages = {
  dashboard: 'Your account is ready. Confirm a prescription to begin building your care overview.',
  scheduler: 'No doses are scheduled yet. Confirm a prescription, then add reminder times.',
  alternatives: 'Search the verified medicine catalog when a reference data source is connected.',
  verification: 'Upload a medicine package to start a new record comparison.',
  reporting: 'Complete a package verification before creating a report draft.',
};

export default function PlaceholderPage({ page, title, description, children }) {
  return (
    <div className="space-y-8">
      <header className="max-w-3xl">
        <p className="mb-3 text-xs font-bold tracking-[0.18em] text-teal-700 uppercase">Your care workspace</p>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">{title}</h1>
        <p className="mt-3 text-base leading-7 text-slate-600">{description}</p>
      </header>
      {page === 'alternatives' && <p className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm font-medium text-amber-950">Confirm with your pharmacist or prescriber before substituting.</p>}
      {page === 'reporting' && <DraftBadge />}
      {children}
      <section className="rounded-2xl border border-slate-200 bg-white p-6" aria-labelledby={`${page}-records-title`}>
        <div className="state-panel" role="status" aria-live="polite">
          <Inbox size={32} className="mx-auto mb-4 text-slate-400" aria-hidden="true" />
          <h2 id={`${page}-records-title`} className="font-semibold text-slate-900">No records yet</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-600">{emptyMessages[page]}</p>
        </div>
      </section>
    </div>
  );
}

export function FeatureLinks({ items }) {
  return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
    {items.map(({ to, label, icon: Icon }) => <Link key={to} to={to} className="group flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-5 transition-colors hover:border-teal-400 hover:bg-teal-50">
      <span className="shrink-0 rounded-xl bg-teal-50 p-3 text-teal-700"><Icon size={22} aria-hidden="true" /></span>
      <span className="min-w-0 flex-1 text-sm font-semibold text-slate-800 wrap-anywhere">{label}</span>
      <ArrowRight size={18} className="shrink-0 text-slate-400 group-hover:text-teal-700" aria-hidden="true" />
    </Link>)}
  </div>;
}
