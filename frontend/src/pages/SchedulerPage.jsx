import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import ErrorMessage from '../components/common/ErrorMessage';
import { DemoBadge } from '../components/common/StatusBadge';
import { EmptyScheduleCard, SchedulerSkeleton } from '../components/scheduler/ScheduleStateCards';
import SimpleMedicineCard from '../components/scheduler/SimpleMedicineCard';
import { dateAtOffset, reminderCount } from '../components/scheduler/schedulerUtils';
import { getPrescriptionSchedule, regenerateScheduleItem, updateScheduleDose, USE_MOCKS } from '../services/api';

const TIMEZONE = 'Asia/Karachi';

function initialTimes(item) {
  if (item.times?.length) return [...item.times];
  return Array.from({ length: Math.max(reminderCount(item.frequency), 1) }, () => '');
}

function activeDose(item) {
  const doses = item.days.flatMap((day) => day.doses).sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
  const today = item.days.find((day) => day.date === dateAtOffset(0))?.doses || [];
  return today.find((dose) => dose.status === 'pending') || today[0] || doses.find((dose) => dose.status === 'pending') || doses[0] || null;
}

export default function SchedulerPage() {
  const [params, setParams] = useSearchParams();
  const requestedId = params.get('prescription_id');
  const [state, setState] = useState({ status: 'loading', data: null, error: null });
  const [timesByItem, setTimesByItem] = useState({});
  const [savingItem, setSavingItem] = useState(null);
  const [busyDose, setBusyDose] = useState(null);
  const [cardErrors, setCardErrors] = useState({});
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setState((current) => ({ status: 'loading', data: current.data, error: null }));
    try {
      const data = await getPrescriptionSchedule(requestedId, TIMEZONE);
      setState({ status: 'success', data, error: null });
      setTimesByItem(Object.fromEntries(data.items.map((item) => [item.prescription_item_id, initialTimes(item)])));
      if (!requestedId && data.prescription_id) setParams({ prescription_id: String(data.prescription_id) }, { replace: true });
    } catch (error) {
      setState({ status: 'error', data: null, error });
    }
  }, [requestedId, setParams]);

  useEffect(() => { load(); }, [load]);

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
    if (!dose || busyDose === dose.id) return;
    const previous = dose;
    setBusyDose(dose.id);
    setCardErrors((current) => ({ ...current, [dose.prescription_item_id]: null }));
    replaceDose(dose.id, { ...dose, status, taken_at: status === 'taken' ? new Date().toISOString() : null });
    setNotice(`Updating ${dose.medicine_name}…`);
    try {
      const updated = await updateScheduleDose(dose.id, status);
      replaceDose(dose.id, { ...dose, ...updated });
      setNotice(`${dose.medicine_name} marked ${status}.`);
    } catch (error) {
      replaceDose(dose.id, previous);
      const message = error?.response?.data?.detail || error.message || 'The medicine status could not be updated.';
      setCardErrors((current) => ({ ...current, [dose.prescription_item_id]: message }));
      setNotice(message);
    } finally {
      setBusyDose(null);
    }
  }

  function updateTime(itemId, index, value) {
    setTimesByItem((current) => ({
      ...current,
      [itemId]: current[itemId].map((time, timeIndex) => timeIndex === index ? value : time),
    }));
  }

  async function saveTimes(item) {
    const times = timesByItem[item.prescription_item_id] || [];
    if (!times.length || times.some((value) => !value)) return;
    setSavingItem(item.prescription_item_id);
    setCardErrors((current) => ({ ...current, [item.prescription_item_id]: null }));
    setNotice(`Saving ${item.medicine_name} reminder…`);
    try {
      await regenerateScheduleItem(item.prescription_item_id, times, TIMEZONE);
      setNotice(`${item.medicine_name} reminder saved.`);
      await load();
    } catch (error) {
      const message = error?.response?.data?.detail || error.message || 'The reminder time could not be saved.';
      setCardErrors((current) => ({ ...current, [item.prescription_item_id]: message }));
      setNotice(message);
    } finally {
      setSavingItem(null);
    }
  }

  return (
    <div className="space-y-6">
      <header className="max-w-3xl">
        <p className="mb-3 text-xs font-bold tracking-[0.18em] text-teal-700 uppercase">Your care workspace</p>
        <h1 className="text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">Medicine scheduler</h1>
        <p className="mt-3 text-base leading-7 text-slate-600">View each medicine, choose its reminder time, and record whether you took it.</p>
      </header>

      <p className="sr-only" role="status" aria-live="polite">{notice}</p>
      {notice && <p className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 shadow-sm" aria-hidden="true">{notice}</p>}

      {state.status === 'loading' && !state.data && <SchedulerSkeleton />}
      {state.status === 'error' && <ErrorMessage title="Could not load your schedule" error={state.error} message={state.error?.message} onRetry={load} />}

      {state.status === 'success' && state.data && (
        <>
          {(USE_MOCKS || state.data.is_demo) && <DemoBadge />}

          {state.data.prescriptions.length > 1 && (
            <label className="block max-w-md text-sm font-semibold text-slate-700">Prescription
              <select value={state.data.prescription_id ?? ''} onChange={(event) => setParams({ prescription_id: event.target.value })} className="mt-2 min-h-11 w-full rounded-xl border border-slate-400 bg-white px-3 text-base">
                {state.data.prescriptions.map((prescription) => <option key={prescription.prescription_id} value={prescription.prescription_id}>Prescription #{prescription.prescription_id}</option>)}
              </select>
            </label>
          )}

          {state.data.items.length === 0 ? <EmptyScheduleCard /> : (
            <section aria-labelledby="medicine-cards-title">
              <h2 id="medicine-cards-title" className="mb-4 text-xl font-bold text-slate-950">Your medicines</h2>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {state.data.items.map((item) => {
                  const dose = activeDose(item);
                  return (
                    <SimpleMedicineCard
                      key={item.prescription_item_id}
                      item={item}
                      times={timesByItem[item.prescription_item_id] || initialTimes(item)}
                      dose={dose}
                      busy={busyDose === dose?.id}
                      saving={savingItem === item.prescription_item_id}
                      error={cardErrors[item.prescription_item_id]}
                      onTimeChange={(index, value) => updateTime(item.prescription_item_id, index, value)}
                      onSaveTimes={() => saveTimes(item)}
                      onStatus={setDoseStatus}
                    />
                  );
                })}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
