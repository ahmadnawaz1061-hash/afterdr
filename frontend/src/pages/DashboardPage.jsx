import { useCallback, useEffect, useState } from 'react';
import { CalendarClock, CheckCircle2, ClipboardList, Clock3, FileHeart, FilePenLine, Pill, RefreshCw, SearchCheck, ShieldCheck, Timer, XCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import Card from '../components/common/Card';
import ErrorMessage from '../components/common/ErrorMessage';
import LoadingState from '../components/common/LoadingState';
import { getDashboard } from '../services/api';

const summaryCards = [
  { label: 'Active prescriptions', field: 'active_prescriptions', icon: ClipboardList, to: '/prescription' },
  { label: 'Doses today', field: 'total_doses', icon: CalendarClock, to: '/scheduler' },
  { label: 'Taken today', field: 'taken', icon: CheckCircle2, to: '/scheduler' },
  { label: 'Missed today', field: 'missed', icon: XCircle, to: '/scheduler' },
  { label: 'Still pending', field: 'remaining', icon: Timer, to: '/scheduler' },
  { label: 'Recent checks', field: 'recent_verifications', icon: SearchCheck, to: '/verification' },
];

const quickActions = [
  { label: 'Read a prescription', to: '/prescription', icon: FileHeart },
  { label: 'Open medicine schedule', to: '/scheduler', icon: CalendarClock },
  { label: 'Find alternatives', to: '/alternatives', icon: Pill },
  { label: 'Check a package', to: '/verification', icon: ShieldCheck },
  { label: 'Prepare a report', to: '/reporting', icon: FilePenLine },
];

function summaryValue(data, field) {
  if (field === 'active_prescriptions' || field === 'recent_verifications') return data[field];
  return data.today[field] ?? 0;
}

function displayTime(value) {
  if (!value) return '';
  const [hours, minutes] = value.split(':').map(Number);
  return `${hours % 12 || 12}:${String(minutes).padStart(2, '0')} ${hours >= 12 ? 'PM' : 'AM'}`;
}

export default function DashboardPage() {
  const [state, setState] = useState({ status: 'loading', data: null, error: null });
  const [lastUpdated, setLastUpdated] = useState(null);

  const load = useCallback(async () => {
    setState((current) => ({ status: current.data ? 'refreshing' : 'loading', data: current.data, error: null }));
    try {
      const data = await getDashboard();
      setState({ status: 'success', data, error: null });
      setLastUpdated(new Date());
    } catch (error) {
      setState((current) => ({ status: 'error', data: current.data, error }));
    }
  }, []);

  useEffect(() => {
    load();
    const refresh = () => load();
    const refreshWhenVisible = () => { if (document.visibilityState === 'visible') load(); };
    const interval = window.setInterval(refresh, 15000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [load]);

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-3xl">
          <p className="mb-3 text-xs font-bold tracking-[0.18em] text-teal-700 uppercase">Your care workspace</p>
          <h1 className="text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">{state.data ? `Welcome, ${state.data.patient.name}` : 'Your dashboard'}</h1>
          <p className="mt-3 text-base leading-7 text-slate-600">Your prescriptions, today's doses, and package checks in one place.</p>
        </div>
        <button type="button" onClick={load} disabled={state.status === 'refreshing'} className="button-secondary gap-2 self-start sm:self-auto"><RefreshCw size={18} className={state.status === 'refreshing' ? 'animate-spin' : ''} aria-hidden="true" />{state.status === 'refreshing' ? 'Refreshing…' : 'Refresh dashboard'}</button>
      </header>

      {lastUpdated && <p className="text-xs font-medium text-slate-500" role="status" aria-live="polite">Updated {lastUpdated.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</p>}
      {state.status === 'loading' && !state.data && <LoadingState title="Loading your dashboard…" message="Gathering your latest records." />}
      {state.status === 'error' && <ErrorMessage title="Could not refresh your dashboard" error={state.error} message={state.error?.message} onRetry={load} />}

      {state.data && (
        <>
          <section aria-labelledby="today-summary-title">
            <h2 id="today-summary-title" className="mb-4 text-xl font-bold text-slate-950">Today's summary</h2>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
              {summaryCards.map(({ label, field, icon: Icon, to }) => (
                <Link key={label} to={to} className="group min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm hover:border-teal-400 hover:shadow-md" aria-label={`${label}: ${summaryValue(state.data, field)}. Open ${to === '/scheduler' ? 'medicine scheduler' : label.toLowerCase()}.`}>
                  <Icon size={21} className="text-teal-700" aria-hidden="true" />
                  <p className="mt-3 text-3xl font-black text-slate-950">{summaryValue(state.data, field)}</p>
                  <h3 className="mt-1 text-xs font-semibold leading-5 text-slate-600 group-hover:text-teal-800">{label}</h3>
                </Link>
              ))}
            </div>
          </section>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card title="Next dose" titleId="next-dose-title" icon={Clock3} footer={<Link to="/scheduler" className="button-secondary">Open medicine schedule</Link>}>
              {state.data.next_dose ? (
                <div>
                  <p className="text-lg font-bold text-slate-950">{state.data.next_dose.medicine}</p>
                  <p className="mt-2 text-sm text-slate-600">Scheduled for <time className="font-bold text-teal-800">{displayTime(state.data.next_dose.time)}</time></p>
                </div>
              ) : <p className="text-sm leading-6 text-slate-600" role="status">No pending dose is scheduled today.</p>}
            </Card>

            <Card title="Quick actions" titleId="quick-actions-title" icon={ClipboardList}>
              <nav className="grid grid-cols-1 gap-2 sm:grid-cols-2" aria-label="Dashboard quick actions">
                {quickActions.map(({ label, to, icon: Icon }) => <Link key={to} to={to} className="inline-flex min-h-11 items-center gap-3 rounded-xl border border-slate-200 px-3 text-sm font-semibold text-slate-700 hover:border-teal-500 hover:bg-teal-50 hover:text-teal-900"><Icon size={18} aria-hidden="true" />{label}</Link>)}
              </nav>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
