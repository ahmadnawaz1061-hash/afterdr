import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, ClipboardCheck } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import Card from '../components/common/Card';
import ErrorMessage from '../components/common/ErrorMessage';
import { DemoBadge } from '../components/common/StatusBadge';
import DoseCard from '../components/scheduler/DoseCard';
import MedicineSetupCard from '../components/scheduler/MedicineSetupCard';
import { ReminderBannerCard, TurnOnRemindersCard } from '../components/scheduler/ReminderCards';
import RoutineCard from '../components/scheduler/RoutineCard';
import { EmptyScheduleCard, SchedulerSkeleton } from '../components/scheduler/ScheduleStateCards';
import SummaryCard from '../components/scheduler/SummaryCard';
import WeekStripCard from '../components/scheduler/WeekStripCard';
import { dateAtOffset, reminderCount } from '../components/scheduler/schedulerUtils';
import { getPrescriptionSchedule, regenerateScheduleItem, updateScheduleDose, USE_MOCKS } from '../services/api';

const TIMEZONE = 'Asia/Karachi';
const ROUTINE_KEY = 'medcare-scheduler-routine';
const ROUTINE_SKIPPED_KEY = 'medcare-scheduler-routine-skipped';

function readRoutine() {
  try {
    return JSON.parse(localStorage.getItem(ROUTINE_KEY)) || {};
  } catch {
    return {};
  }
}

function notificationState() {
  return typeof window !== 'undefined' && 'Notification' in window ? window.Notification.permission : 'unsupported';
}

function initialSetup(item) {
  const count = reminderCount(item.frequency);
  return {
    times: item.times?.length ? [...item.times] : Array.from({ length: count }, () => ''),
    startDate: item.course_start || dateAtOffset(0),
    durationDays: item.duration_days || '',
    skipped: false,
  };
}

function setupReady(item, setup) {
  if (!setup || setup.skipped) return Boolean(setup?.skipped);
  const count = reminderCount(item.frequency);
  return count > 0
    && setup.times.length === count
    && setup.times.every(Boolean)
    && Boolean(setup.startDate)
    && Number(setup.durationDays) > 0;
}

export default function SchedulerPage() {
  const [params, setParams] = useSearchParams();
  const requestedId = params.get('prescription_id');
  const [state, setState] = useState({ status: 'loading', data: null, error: null });
  const [setups, setSetups] = useState({});
  const [routine, setRoutine] = useState(readRoutine);
  const [showRoutine, setShowRoutine] = useState(() => localStorage.getItem(ROUTINE_SKIPPED_KEY) !== 'true');
  const [selectedDay, setSelectedDay] = useState(dateAtOffset(0));
  const [notice, setNotice] = useState('');
  const [dueDose, setDueDose] = useState(null);
  const [permission, setPermission] = useState(notificationState);
  const [savingAll, setSavingAll] = useState(false);
  const [busyDoseIds, setBusyDoseIds] = useState(new Set());
  const [doseErrors, setDoseErrors] = useState({});
  const notifiedDoseIds = useRef(new Set());
  const snoozedUntil = useRef(new Map());

  const load = useCallback(async () => {
    setState((current) => ({ status: 'loading', data: current.data, error: null }));
    try {
      const data = await getPrescriptionSchedule(requestedId, TIMEZONE);
      setState({ status: 'success', data, error: null });
      setSetups(Object.fromEntries(data.items.map((item) => [item.prescription_item_id, initialSetup(item)])));
      if (!requestedId && data.prescription_id) setParams({ prescription_id: String(data.prescription_id) }, { replace: true });
    } catch (error) {
      setState({ status: 'error', data: null, error });
    }
  }, [requestedId, setParams]);

  useEffect(() => { load(); }, [load]);

  const groupedDays = useMemo(() => {
    const groups = new Map();
    for (const item of state.data?.items || []) {
      for (const day of item.days) groups.set(day.date, [...(groups.get(day.date) || []), ...day.doses]);
    }
    return groups;
  }, [state.data]);

  const allDoses = useMemo(() => [...groupedDays.values()].flat(), [groupedDays]);
  const todayDoses = groupedDays.get(dateAtOffset(0)) || [];
  const selectedDoses = useMemo(
    () => [...(groupedDays.get(selectedDay) || [])].sort((a, b) => a.local_time.localeCompare(b.local_time)),
    [groupedDays, selectedDay],
  );
  const nextDose = useMemo(
    () => [...todayDoses].filter((dose) => dose.status === 'pending').sort((a, b) => a.local_time.localeCompare(b.local_time))[0] || null,
    [todayDoses],
  );
  const allItemsReady = Boolean(state.data?.items.length)
    && state.data.items.every((item) => setupReady(item, setups[item.prescription_item_id]));

  useEffect(() => {
    function checkDueDoses() {
      const now = Date.now();
      const due = allDoses.filter((dose) => {
        if (dose.status !== 'pending') return false;
        const elapsed = now - new Date(dose.scheduled_at).getTime();
        return elapsed >= 0 && elapsed <= 2 * 60 * 60 * 1000 && (snoozedUntil.current.get(dose.id) || 0) <= now;
      }).sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at))[0];
      if (!due) return;
      setDueDose(due);
      if (!notifiedDoseIds.current.has(due.id)) {
        notifiedDoseIds.current.add(due.id);
        if (permission === 'granted') new window.Notification('Medicine reminder', { body: `${due.medicine_name} is due now${due.dose ? `: ${due.dose}` : ''}.`, tag: `medcare-dose-${due.id}` });
      }
    }
    checkDueDoses();
    const interval = window.setInterval(checkDueDoses, 30000);
    return () => window.clearInterval(interval);
  }, [allDoses, permission]);

  function replaceDose(doseId, replacement) {
    setState((current) => ({
      ...current,
      data: {
        ...current.data,
        items: current.data.items.map((item) => ({
          ...item,
          days: item.days.map((day) => ({ ...day, doses: day.doses.map((dose) => dose.id === doseId ? replacement : dose) })),
        })),
      },
    }));
  }

  async function setDoseStatus(dose, status) {
    if (busyDoseIds.has(dose.id)) return;
    const previous = dose;
    setBusyDoseIds((current) => new Set(current).add(dose.id));
    setDoseErrors((current) => ({ ...current, [dose.id]: null }));
    replaceDose(dose.id, { ...dose, status, taken_at: status === 'taken' ? new Date().toISOString() : null });
    setNotice(`Updating ${dose.medicine_name}…`);
    try {
      const updated = await updateScheduleDose(dose.id, status);
      replaceDose(dose.id, { ...dose, ...updated });
      setDueDose((current) => current?.id === dose.id ? null : current);
      setNotice(`${dose.medicine_name} marked ${status}.`);
    } catch (error) {
      replaceDose(dose.id, previous);
      const message = error?.response?.data?.detail || error.message || 'The dose status could not be updated.';
      setDoseErrors((current) => ({ ...current, [dose.id]: message }));
      setNotice(message);
    } finally {
      setBusyDoseIds((current) => {
        const next = new Set(current);
        next.delete(dose.id);
        return next;
      });
    }
  }

  function updateSetup(itemId, changes) {
    setSetups((current) => ({ ...current, [itemId]: { ...current[itemId], ...changes } }));
  }

  function updateRoutine(key, value) {
    setRoutine((current) => {
      const next = { ...current, [key]: value };
      localStorage.setItem(ROUTINE_KEY, JSON.stringify(next));
      return next;
    });
  }

  function skipRoutine() {
    localStorage.setItem(ROUTINE_SKIPPED_KEY, 'true');
    setShowRoutine(false);
  }

  function copyTimes(sourceId) {
    const times = setups[sourceId]?.times || [];
    setSetups((current) => Object.fromEntries(Object.entries(current).map(([id, setup]) => [id, Number(id) === sourceId ? setup : { ...setup, times: [...times], skipped: false }])));
    setNotice('Reminder times copied to the other medicine cards.');
  }

  function toggleSkip(itemId) {
    updateSetup(itemId, { skipped: !setups[itemId]?.skipped });
  }

  async function createSchedule() {
    if (!allItemsReady) return;
    setSavingAll(true);
    setNotice('Creating your schedule…');
    try {
      for (const item of state.data.items) {
        const setup = setups[item.prescription_item_id];
        if (!setup.skipped) await regenerateScheduleItem(item.prescription_item_id, setup.times, TIMEZONE);
      }
      setNotice('Your medicine schedule is ready.');
      await load();
    } catch (error) {
      setNotice(error?.response?.data?.detail || error.message || 'Your schedule could not be created.');
    } finally {
      setSavingAll(false);
    }
  }

  async function enableNotifications() {
    try {
      const result = await window.Notification.requestPermission();
      setPermission(result);
      setNotice(result === 'granted' ? 'Browser reminders are on.' : 'Browser reminders were not enabled.');
    } catch {
      setPermission('denied');
      setNotice('Browser reminders are unavailable.');
    }
  }

  function snoozeDose() {
    if (!dueDose) return;
    snoozedUntil.current.set(dueDose.id, Date.now() + 10 * 60 * 1000);
    notifiedDoseIds.current.delete(dueDose.id);
    setNotice(`${dueDose.medicine_name} snoozed for 10 minutes.`);
    setDueDose(null);
  }

  return (
    <div className="space-y-5 pb-28 md:space-y-6 md:pb-0">
      <header className="max-w-3xl">
        <p className="mb-3 text-xs font-bold tracking-[0.18em] text-teal-700 uppercase">Your care workspace</p>
        <h1 className="text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">Medicine scheduler</h1>
        <p className="mt-3 text-base leading-7 text-slate-600">Choose your own reminder times and track every dose in one place.</p>
      </header>

      <p className="sr-only" role="status" aria-live="polite">{notice}</p>
      {notice && <p className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 shadow-sm" aria-hidden="true">{notice}</p>}
      {state.status === 'loading' && !state.data && <SchedulerSkeleton />}
      {state.status === 'error' && <Card title="Schedule unavailable" titleId="schedule-error-title" icon={ClipboardCheck}><ErrorMessage title="Could not load your schedule" error={state.error} message={state.error?.message} onRetry={load} /></Card>}

      {state.status === 'success' && state.data && (
        <>
          <ReminderBannerCard dose={dueDose} onTaken={() => setDoseStatus(dueDose, 'taken')} onSnooze={snoozeDose} onSkip={() => setDoseStatus(dueDose, 'missed')} />
          {permission === 'default' && <TurnOnRemindersCard onEnable={enableNotifications} />}
          {(USE_MOCKS || state.data.is_demo) && <DemoBadge />}

          {state.data.items.length === 0 ? <EmptyScheduleCard /> : (
            <>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <SummaryCard total={todayDoses.length} taken={todayDoses.filter((dose) => dose.status === 'taken').length} nextDose={nextDose} />
                <WeekStripCard selectedDay={selectedDay} onSelectDay={setSelectedDay} />
              </div>

              {state.data.prescriptions.length > 0 && (
                <Card title="Confirmed prescription" titleId="prescription-choice-title" icon={ClipboardCheck}>
                  <label className="block max-w-md text-sm font-semibold text-slate-700">Prescription used for this schedule
                    <select value={state.data.prescription_id ?? ''} onChange={(event) => setParams({ prescription_id: event.target.value })} className="mt-2 min-h-11 w-full rounded-xl border border-slate-400 bg-white px-3 text-base">
                      {state.data.prescriptions.map((prescription) => <option key={prescription.prescription_id} value={prescription.prescription_id}>Prescription #{prescription.prescription_id} · {new Date(prescription.created_at).toLocaleDateString()}</option>)}
                    </select>
                  </label>
                </Card>
              )}

              {showRoutine && <RoutineCard routine={routine} onChange={updateRoutine} onSkip={skipRoutine} />}

              <section aria-labelledby="medicine-setup-title">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div><h2 id="medicine-setup-title" className="text-xl font-bold text-slate-950">Set up your medicines</h2><p className="mt-1 text-sm text-slate-600">Times stay empty until you choose them.</p></div>
                  {state.data.items.every((item) => setupReady(item, setups[item.prescription_item_id])) && <span className="inline-flex items-center gap-1.5 text-sm font-bold text-emerald-800"><CheckCircle2 size={18} aria-hidden="true" />Ready</span>}
                </div>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  {state.data.items.map((item) => <MedicineSetupCard key={item.prescription_item_id} item={item} setup={setups[item.prescription_item_id] || initialSetup(item)} routine={routine} onChange={(changes) => updateSetup(item.prescription_item_id, changes)} onCopy={copyTimes} onSkip={toggleSkip} />)}
                </div>
              </section>

              <section aria-labelledby="daily-doses-title">
                <div className="mb-4"><h2 id="daily-doses-title" className="text-xl font-bold text-slate-950">Doses for {selectedDay === dateAtOffset(0) ? 'today' : selectedDay}</h2><p className="mt-1 text-sm text-slate-600">Sorted by reminder time.</p></div>
                {selectedDoses.length ? <div className="grid grid-cols-1 gap-4">{selectedDoses.map((dose) => <DoseCard key={dose.id} dose={dose} onStatus={setDoseStatus} busy={busyDoseIds.has(dose.id)} error={doseErrors[dose.id]} />)}</div> : <Card title="No doses on this day" titleId="no-doses-day-title" icon={ClipboardCheck}><p className="text-sm text-slate-600">Choose another day or finish setting up the medicine cards above.</p></Card>}
              </section>

              <div className="fixed inset-x-0 bottom-16 z-30 border-t border-slate-200 bg-white/95 p-3 shadow-[0_-8px_24px_rgba(15,23,42,0.08)] backdrop-blur md:static md:rounded-2xl md:border md:p-4 md:shadow-sm">
                <div className="mx-auto flex max-w-5xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-center text-xs font-semibold text-slate-600 sm:text-left">{allItemsReady ? 'Every medicine is ready or skipped.' : 'Complete or skip every medicine card to continue.'}</p>
                  <button type="button" disabled={!allItemsReady || savingAll} onClick={createSchedule} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-teal-800 px-6 text-base font-bold text-white hover:bg-teal-900 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600"><ClipboardCheck size={20} aria-hidden="true" />{savingAll ? 'Creating schedule…' : 'Create my schedule'}</button>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
