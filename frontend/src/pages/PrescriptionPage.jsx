import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, FileSearch } from 'lucide-react';
import FileUploader from '../components/common/FileUploader';
import LoadingState from '../components/common/LoadingState';
import ErrorMessage from '../components/common/ErrorMessage';
import { DemoBadge } from '../components/common/StatusBadge';
import { extractPrescription, savePrescription } from '../services/api';

const fields = [
  ['name', 'Medicine'],
  ['strength', 'Strength'],
  ['dose', 'Dose'],
  ['frequency', 'Frequency'],
  ['duration_days', 'Duration (days)'],
  ['instructions', 'Instructions'],
];

export default function PrescriptionPage() {
  const [file, setFile] = useState(null);
  const [state, setState] = useState('empty');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const [saving, setSaving] = useState(false);
  const requestId = useRef(0);
  const resultRef = useRef(null);

  useEffect(() => () => { requestId.current += 1; }, []);

  function handleFileSelect(nextFile) {
    requestId.current += 1;
    setFile(nextFile);
    setResult(null);
    setError(null);
    setSaveError(null);
    setSaving(false);
    setState('empty');
  }

  async function readPrescription() {
    if (!file || state === 'loading') return;
    const currentRequest = ++requestId.current;
    setState('loading');
    setError(null);
    try {
      const data = await extractPrescription(file);
      if (!data || !Array.isArray(data.medicines)) throw new Error('The server returned an invalid prescription result.');
      if (currentRequest !== requestId.current) return;
      setResult(data);
      setState(data.medicines.length ? 'success' : 'empty-result');
      requestAnimationFrame(() => resultRef.current?.focus({ preventScroll: true }));
    } catch (requestError) {
      if (currentRequest !== requestId.current) return;
      setError(requestError);
      setState('error');
      requestAnimationFrame(() => resultRef.current?.focus({ preventScroll: true }));
    }
  }

  function updateMedicine(index, field, value) {
    setResult((current) => ({
      ...current,
      medicines: current.medicines.map((medicine, medicineIndex) => medicineIndex === index
        ? { ...medicine, [field]: field === 'duration_days' ? Number(value) || '' : value }
        : medicine),
    }));
  }

  async function confirmPrescription() {
    if (!result || saving) return;
    setSaving(true);
    setSaveError(null);
    const reviewedMedicines = result.medicines.map((medicine) => ({
      name: medicine.name,
      strength: medicine.strength || null,
      dose: medicine.dose || null,
      frequency: medicine.frequency || null,
      duration_days: medicine.duration_days || null,
      instructions: medicine.instructions || null,
      needs_review: false,
      is_demo: false,
    }));
    try {
      const saved = await savePrescription({
        patient_name: result.patient_name || null,
        doctor_name: result.doctor_name || null,
        status: 'confirmed',
        medicines: reviewedMedicines,
      });
      setResult((current) => ({
        ...current,
        ...saved,
        medicines: reviewedMedicines,
      }));
    } catch (requestError) {
      setSaveError(requestError);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <header className="max-w-3xl">
        <p className="mb-3 text-xs font-bold tracking-[0.18em] text-teal-700 uppercase">Your care companion</p>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Prescription reader</h1>
        <p className="mt-3 text-base leading-7 text-slate-600">Upload a prescription image, then review and correct every instruction before confirming it.</p>
      </header>

      <section aria-labelledby="upload-title" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <h2 id="upload-title" className="text-lg font-semibold text-slate-900">1. Add a prescription image</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">The extraction is a review draft. Check it against the prescription image.</p>
        <div className="mt-5"><FileUploader label="Prescription image" disabled={state === 'loading'} onFileSelect={handleFileSelect} /></div>
        <button type="button" onClick={readPrescription} disabled={!file || state === 'loading'}
          className="mt-5 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-teal-800 px-5 py-3 text-sm font-semibold text-white hover:bg-teal-900 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600 sm:w-auto">
          <FileSearch size={18} aria-hidden="true" />{state === 'loading' ? 'Reading prescription…' : 'Read prescription'}
        </button>
      </section>

      <section ref={resultRef} tabIndex={-1} aria-labelledby="review-title" className="rounded-2xl border border-slate-200 bg-white p-5 focus-visible:outline-offset-[-3px] sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 id="review-title" className="text-lg font-semibold text-slate-900">2. Review extracted instructions</h2><p className="mt-2 text-sm text-slate-600">Correct unclear fields before confirming.</p></div>
          {result?.is_demo && <DemoBadge />}
        </div>

        {state === 'loading' && <LoadingState title="Reading the prescription…" message="Extracting visible medicine instructions for your review." />}
        {state === 'error' && <ErrorMessage title="Could not read the prescription" error={error} message={error?.message || 'Please check the backend and try again.'} onRetry={readPrescription} />}
        {state === 'empty' && <div className="state-panel" role="status" aria-live="polite"><FileSearch size={32} className="mx-auto mb-4 text-slate-400" aria-hidden="true" /><p className="text-sm text-slate-600">Choose an image and select “Read prescription” to begin.</p></div>}
        {state === 'empty-result' && <div className="state-panel" role="status" aria-live="polite"><p className="text-sm text-slate-600">No medicine instructions were found. Try a clearer image.</p></div>}
        {state === 'success' && <div className="mt-5 space-y-4" aria-live="polite">
          {result.simulated && <p className="text-sm text-slate-600">This extraction was generated by the backend demonstration stub.</p>}
          {result.medicines.map((medicine, index) => <fieldset key={index} className={`rounded-xl border p-4 ${medicine.needs_review ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-white'}`}>
            <legend className="px-2 text-sm font-semibold text-slate-900">Medicine {index + 1}{medicine.needs_review ? ' · Needs review' : ''}</legend>
            <div className="mt-2 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {fields.map(([field, label]) => <label key={field} className="block text-sm font-medium text-slate-700">
                {label}
                <input type={field === 'duration_days' ? 'number' : 'text'} min={field === 'duration_days' ? 1 : undefined}
                  value={medicine[field] ?? ''} onChange={(event) => updateMedicine(index, field, event.target.value)}
                  className="mt-2 min-h-11 w-full rounded-lg border border-slate-500 bg-white px-3 text-base text-slate-900 sm:text-sm" />
              </label>)}
            </div>
          </fieldset>)}
          {saveError && <ErrorMessage title="Could not save the prescription" error={saveError} message={saveError?.message || 'Please try again.'} />}
          {result.status !== 'confirmed' && <button type="button" onClick={confirmPrescription} disabled={saving} className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-teal-800 px-5 py-3 text-sm font-semibold text-white hover:bg-teal-900 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600 sm:w-auto">
            <CheckCircle2 size={18} aria-hidden="true" />{saving ? 'Saving prescription…' : 'Confirm reviewed instructions'}
          </button>}
        </div>}
        {result?.status === 'confirmed' && <div role="status" aria-live="polite" className="mt-5 rounded-xl border border-teal-200 bg-teal-50 p-4 text-sm font-medium text-teal-900">Prescription saved to your account.</div>}
      </section>
    </div>
  );
}
