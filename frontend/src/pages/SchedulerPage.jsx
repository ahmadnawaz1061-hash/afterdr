import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarClock, Plus, RotateCcw } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import ErrorMessage from '../components/common/ErrorMessage';
import LoadingState from '../components/common/LoadingState';
import StatusBadge, { DemoBadge } from '../components/common/StatusBadge';
import { getPrescriptionSchedule, regenerateScheduleItem, updateScheduleDose, USE_MOCKS } from '../services/api';

const TIMEZONE = 'Asia/Karachi';

function localToday() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date());
}

export default function SchedulerPage() {
  const [params, setParams] = useSearchParams();
  const requestedId = params.get('prescription_id');
  const [state, setState] = useState({ status: 'loading', data: null, error: null });
  const [edits, setEdits] = useState({});
  const [savingItem, setSavingItem] = useState(null);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setState((current) => ({ status: 'loading', data: current.data, error: null }));
    try {
      const data = await getPrescriptionSchedule(requestedId, TIMEZONE);
      setState({ status: 'success', data, error: null });
      setEdits(Object.fromEntries(data.items.map((item) => [
        item.prescription_item_id,
        item.times.length ? item.times : item.suggested_times.length ? item.suggested_times : ['09:00'],
      ])));
      if (!requestedId && data.prescription_id) {
        setParams({ prescription_id: String(data.prescription_id) }, { replace: true });
      }
    } catch (error) {
      setState({ status: 'error', data: null, error });
    }
  }, [requestedId, setParams]);

  useEffect(() => { load(); }, [load]);

  function updateTime(itemId, index, value) {
    setEdits((current) => ({
      ...current,
      [itemId]: current[itemId].map((time, timeIndex) => timeIndex === index ? value : time),
    }));
  }

  function addTime(itemId) {
    setEdits((current) => ({ ...current, [itemId]: [...(current[itemId] || []), '09:00'] }));
  }

  function removeTime(itemId, index) {
    setEdits((current) => ({
      ...current,
      [itemId]: current[itemId].filter((_, timeIndex) => timeIndex !== index),
    }));
  }

  async function saveTimes(item) {
    const times = [...new Set((edits[item.prescription_item_id] || []).filter(Boolean))];
    if (!times.length) {
      setNotice(`${item.medicine_name}: choose at least one reminder time.`);
      return;
    }
    setSavingItem(item.prescription_item_id);
    setNotice('');
    try {
      await regenerateScheduleItem(item.prescription_item_id, times, TIMEZONE);
      setNotice(`${item.medicine_name}: reminder times updated.`);
      await load();
    } catch (error) {
      setNotice(error?.response?.data?.detail || error.message || 'The reminder times could not be updated.');
    } finally {
      setSavingItem(null);
    }
  }

  function replaceDose(doseId, replacement) {
    setState((current) => ({
      ...current,
      data: {
        ...current.data,
        items: current.data.items.map((item) => ({
          ...item,
          days: item.days.map((day) => ({
            ...day,
            doses: day.doses.map((dose) => dose.id === doseId ? replacement : dose),
          })),
        })),
      },
    }));
  }

  async function setDoseStatus(dose, status) {
    const previous = dose;
    replaceDose(dose.id, { ...dose, status, taken_at: status === 'taken' ? new Date().toISOString() : null });
    setNotice(`Updating ${dose.medicine_name}…`);
    try {
      const updated = await updateScheduleDose(dose.id, status);
      replaceDose(dose.id, updated);
      setNotice(`${dose.medicine_name} marked ${status}.`);
    } catch (error) {
      replaceDose(dose.id, previous);
      setNotice(error?.response?.data?.detail || error.message || 'The dose status could not be updated.');
    }
  }

  const groupedDays = useMemo(() => {
    if (!state.data) return [];
    const groups = new Map();
    for (const item of state.data.items) {
      for (const day of item.days) {
        groups.set(day.date, [...(groups.get(day.date) || []), ...day.doses]);
      }
    }
    const today = localToday();
    return [...groups.entries()].sort(([a], [b]) => {
      if (a === today) return -1;
      if (b === today) return 1;
      return a.localeCompare(b);
    });
  }, [state.data]);

  const todaySummary = useMemo(() => {
    const doses = groupedDays.find(([day]) => day === localToday())?.[1] || [];
    return {
      total: doses.length,
      taken: doses.filter((dose) => dose.status === 'taken').length,
      missed: doses.filter((dose) => dose.status === 'missed').length,
      remaining: doses.filter((dose) => dose.status === 'pending').length,
    };
  }, [groupedDays]);

  return <div className="space-y-8">
    <header className="max-w-3xl">
      <p className="mb-3 text-xs font-bold tracking-[0.18em] text-teal-700 uppercase">Your care workspace</p>
      <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Medicine scheduler</h1>
      <p className="mt-3 text-base leading-7 text-slate-600">Review suggested times and track each scheduled dose.</p>
    </header>

    <p className="rounded-xl border border-sky-200 bg-sky-50 px-5 py-4 text-sm font-medium leading-6 text-sky-950">
      Schedule created automatically from your confirmed prescription. Times are suggestions. Edit them if they don't suit you.
    </p>
    <p className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-950">Reminders work inside this app only. Keep the page open, as notifications are not sent when it is closed.</p>
    <p className="sr-only" role="status" aria-live="polite">{notice}</p>
    {notice && <p className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700" aria-hidden="true">{notice}</p>}

    {state.status === 'loading' && !state.data && <LoadingState title="Loading your schedule…" message="Gathering your confirmed medicines and doses." />}
    {state.status === 'error' && <ErrorMessage title="Could not load your schedule" error={state.error} message={state.error?.message} onRetry={load} />}
    {state.status === 'success' && state.data && <>
      {(USE_MOCKS || state.data.is_demo) && <DemoBadge />}
      {state.data.prescriptions.length > 0 && <label className="block max-w-md text-sm font-semibold text-slate-700">
        Confirmed prescription
        <select value={state.data.prescription_id ?? ''} onChange={(event) => setParams({ prescription_id: event.target.value })} className="mt-2 min-h-11 w-full rounded-xl border border-slate-400 bg-white px-3 text-base">
          {state.data.prescriptions.map((prescription) => <option key={prescription.prescription_id} value={prescription.prescription_id}>Prescription #{prescription.prescription_id} · {new Date(prescription.created_at).toLocaleDateString()}</option>)}
        </select>
      </label>}

      {state.data.items.length === 0 ? <section className="state-panel rounded-2xl border border-slate-200 bg-white" role="status" aria-live="polite">
        <CalendarClock size={32} className="mx-auto mb-4 text-slate-400" aria-hidden="true" />
        <h2 className="font-semibold text-slate-900">No confirmed prescription yet</h2>
        <p className="mt-2 text-sm text-slate-600">Confirm a reviewed prescription to create your schedule.</p>
        <Link to="/prescription" className="button-secondary mt-5">Go to Prescription Reader</Link>
      </section> : <>
        <section aria-label="Today’s dose summary" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(todaySummary).map(([label, value]) => <div key={label} className="rounded-xl border border-slate-200 bg-white p-4"><p className="text-2xl font-bold text-slate-900">{value}</p><p className="mt-1 text-xs font-semibold capitalize text-slate-600">{label}</p></div>)}
        </section>

        <section className="space-y-4" aria-labelledby="medicine-times-title">
          <h2 id="medicine-times-title" className="text-xl font-bold text-slate-900">Medicine reminder times</h2>
          {state.data.items.map((item) => <article key={item.prescription_item_id} className={`rounded-2xl border bg-white p-5 sm:p-6 ${item.status === 'needs_times' ? 'border-amber-300' : 'border-slate-200'}`}>
            <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold text-slate-900">{item.medicine_name}</h3><p className="mt-1 text-sm text-slate-600">{item.dose || 'Dose not provided'} · {item.frequency || 'Frequency needs review'}</p></div>{item.is_demo && <DemoBadge />}</div>
            <p className="mt-3 text-sm text-slate-600">Course: {item.course_start || 'Not set'} to {item.course_end || 'Not set'}</p>
            {item.status === 'needs_times' && <p className="mt-3 rounded-lg bg-amber-50 px-4 py-3 text-sm font-medium text-amber-950">{item.reason || 'Choose reminder times before scheduling this medicine.'}</p>}
            <div className="mt-4 flex flex-wrap gap-3">
              {(edits[item.prescription_item_id] || []).map((value, index) => <div key={`${item.prescription_item_id}-${index}`} className="flex items-center gap-2 rounded-xl bg-slate-100 p-2">
                <label className="sr-only" htmlFor={`time-${item.prescription_item_id}-${index}`}>Reminder time {index + 1} for {item.medicine_name}</label>
                <input id={`time-${item.prescription_item_id}-${index}`} type="time" value={value} onChange={(event) => updateTime(item.prescription_item_id, index, event.target.value)} className="min-h-11 rounded-lg border border-slate-400 bg-white px-3 text-base" />
                <button type="button" onClick={() => removeTime(item.prescription_item_id, index)} className="min-h-11 rounded-lg px-3 text-sm font-semibold text-rose-800 hover:bg-rose-50" aria-label={`Remove reminder time ${index + 1} for ${item.medicine_name}`}>Remove</button>
              </div>)}
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <button type="button" onClick={() => addTime(item.prescription_item_id)} className="button-secondary gap-2"><Plus size={16} aria-hidden="true" />Add time</button>
              <button type="button" disabled={savingItem === item.prescription_item_id} onClick={() => saveTimes(item)} className="inline-flex min-h-11 items-center justify-center rounded-xl bg-teal-800 px-5 py-2 text-sm font-semibold text-white hover:bg-teal-900 disabled:bg-slate-400">{savingItem === item.prescription_item_id ? 'Saving…' : item.status === 'needs_times' ? 'Set times' : 'Save new times'}</button>
              <button type="button" disabled={!item.suggested_times.length} onClick={() => setEdits((current) => ({ ...current, [item.prescription_item_id]: item.suggested_times }))} className="button-secondary gap-2 disabled:cursor-not-allowed disabled:opacity-50"><RotateCcw size={16} aria-hidden="true" />Reset to suggested</button>
            </div>
          </article>)}
        </section>

        <section className="space-y-4" aria-labelledby="daily-view-title">
          <h2 id="daily-view-title" className="text-xl font-bold text-slate-900">Daily doses</h2>
          {groupedDays.length === 0 ? <p className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600">No doses have been generated yet. Set reminder times above.</p> : groupedDays.map(([day, doses]) => <article key={day} className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
            <h3 className="font-semibold text-slate-900">{day === localToday() ? `Today · ${day}` : day}</h3>
            <ul className="mt-4 divide-y divide-slate-200">{doses.map((dose) => <li key={dose.id} className="py-4 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-medium text-slate-900">{dose.medicine_name}</p><p className="mt-1 text-sm text-slate-600"><time>{dose.local_time}</time></p></div><StatusBadge status={dose.status} /></div>
              <div className="mt-3 grid grid-cols-3 gap-2" role="group" aria-label={`Set status for ${dose.medicine_name} at ${dose.local_time}`}>
                {['taken', 'missed', 'pending'].map((status) => <button key={status} type="button" aria-pressed={dose.status === status} onClick={() => setDoseStatus(dose, status)} className="min-h-11 rounded-lg border border-slate-400 bg-white px-2 text-xs font-semibold capitalize text-slate-700 hover:bg-slate-50 aria-pressed:border-teal-700 aria-pressed:bg-teal-50 aria-pressed:text-teal-900">{status}</button>)}
              </div>
            </li>)}</ul>
          </article>)}
        </section>
      </>}
    </>}
  </div>;
}
