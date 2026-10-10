import { useCallback, useEffect, useState } from 'react';
import { CalendarClock, CheckCircle2, ClipboardList, Clock3, SearchCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import ErrorMessage from '../components/common/ErrorMessage';
import LoadingState from '../components/common/LoadingState';
import { getDashboard } from '../services/api';

export default function DashboardPage() {
  const [state, setState] = useState({ status: 'loading', data: null, error: null });

  const load = useCallback(async () => {
    setState({ status: 'loading', data: null, error: null });
    try {
      const data = await getDashboard();
      setState({ status: 'success', data, error: null });
    } catch (error) {
      setState({ status: 'error', data: null, error });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return <div className="space-y-8">
    <header className="max-w-3xl">
      <p className="mb-3 text-xs font-bold tracking-[0.18em] text-teal-700 uppercase">Your care workspace</p>
      <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">{state.data ? `Welcome, ${state.data.patient.name}` : 'Your dashboard'}</h1>
      <p className="mt-3 text-base leading-7 text-slate-600">Your prescriptions, today’s doses, and recent package checks in one place.</p>
    </header>

    {state.status === 'loading' && <LoadingState title="Loading your dashboard…" message="Gathering your latest records." />}
    {state.status === 'error' && <ErrorMessage title="Could not load your dashboard" error={state.error} message={state.error?.message} onRetry={load} />}
    {state.status === 'success' && <>
      <section aria-label="Today’s summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['Active prescriptions', state.data.active_prescriptions, ClipboardList],
          ['Doses today', state.data.today.total_doses, CalendarClock],
          ['Taken today', state.data.today.taken, CheckCircle2],
          ['Recent checks', state.data.recent_verifications, SearchCheck],
        ].map(([label, value, Icon]) => <article key={label} className="rounded-2xl border border-slate-200 bg-white p-5">
          <Icon size={22} className="text-teal-700" aria-hidden="true" />
          <p className="mt-4 text-3xl font-bold text-slate-900">{value}</p>
          <h2 className="mt-1 text-sm font-medium text-slate-600">{label}</h2>
        </article>)}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6" aria-labelledby="next-dose-title">
        <div className="flex items-center gap-3"><Clock3 className="text-teal-700" aria-hidden="true" /><h2 id="next-dose-title" className="text-lg font-semibold text-slate-900">Next dose</h2></div>
        {state.data.next_dose
          ? <p className="mt-4 text-slate-700"><strong>{state.data.next_dose.medicine}</strong> at <time>{state.data.next_dose.time}</time></p>
          : <div className="mt-4" role="status" aria-live="polite"><p className="text-sm text-slate-600">No pending dose is scheduled today.</p><Link to="/prescription" className="button-secondary mt-4 inline-flex">Add a prescription</Link></div>}
      </section>
    </>}
  </div>;
}
