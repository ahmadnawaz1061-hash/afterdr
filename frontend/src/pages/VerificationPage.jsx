import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, CheckCircle2, ChevronDown, Clock3, Lightbulb, LoaderCircle, ShieldCheck, Sparkles } from 'lucide-react';
import ErrorMessage from '../components/common/ErrorMessage';
import { DemoBadge } from '../components/common/StatusBadge';
import PackagingUploadCard from '../components/verification/PackagingUploadCard';
import PackagingResults from '../components/verification/PackagingResults';
import { MAX_UPLOAD_TOTAL, validatePackagingFile } from '../components/verification/packagingUploads';
import { analyzePackage, reanalyzeVerification, listVerifications, getVerification } from '../services/api';

const slots = [
  { id: 'front', title: 'Front of pack', requirement: 'Required', hint: 'Keep the product name and main label fully visible.' },
  { id: 'back', title: 'Back or side', requirement: 'Recommended', hint: 'Capture the ingredient and manufacturer information.' },
  { id: 'closeup', title: 'Close-up of label or logo', requirement: 'Optional', hint: 'Focus on text or design details you want inspected.' },
];
const correctionLabels = { brand_name: 'Brand name', manufacturer: 'Manufacturer', registration_number: 'Registration number' };
const processingStages = ['Validating images', 'Reading packaging text and inspecting visual details', 'Searching online product references and comparing available information', 'Preparing assessment'];
const cancelled = (error) => ['AbortError', 'CanceledError'].includes(error?.name) || error?.code === 'ERR_CANCELED';

export default function VerificationPage() {
  const navigate = useNavigate();
  const [photos, setPhotos] = useState([null, null, null]);
  const [manualFields, setManualFields] = useState({});
  const [fields, setFields] = useState({});
  const [step, setStep] = useState('upload');
  const [stage, setStage] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState(null);
  const [opening, setOpening] = useState(null);
  const request = useRef({ id: 0, controller: null });
  const resultRef = useRef(null);
  const uploadRef = useRef(null);
  const working = useRef(false);
  const retryAction = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    listVerifications({ signal: controller.signal }).then(setHistory).catch((problem) => { if (!cancelled(problem)) setHistoryError(problem); });
    return () => { controller.abort(); request.current.id += 1; request.current.controller?.abort(); };
  }, []);
  useEffect(() => {
    if (step === 'result') { resultRef.current?.focus({ preventScroll: true }); resultRef.current?.scrollIntoView?.({ block: 'start', behavior: 'instant' }); }
  }, [step, result?.verification_id]);

  function startRequest() {
    request.current.controller?.abort();
    request.current = { id: request.current.id + 1, controller: new AbortController() };
    // Capture the request ID by value; canceling mutates the live ref.
    return { ...request.current };
  }
  function installResult(data) {
    setResult(data); setFields(data.extracted); setStep('result');
    setHistory((previous) => [{ verification_id: data.verification_id, brand_name: data.extracted.brand_name, status: data.status, status_label: data.status_label, risk_level: data.risk_level, risk_score: data.risk_score, simulated: data.simulated, assessed_at: data.assessed_at }, ...previous.filter((item) => item.verification_id !== data.verification_id)].slice(0, 10));
  }
  function cancelAnalysis() {
    request.current.id += 1; request.current.controller?.abort(); working.current = false;
    setStep(result ? 'result' : 'upload'); setUpdating(false); setOpening(null); setError(null);
  }
  async function runAnalysis() {
    if (!photos[0] || working.current) return;
    retryAction.current = runAnalysis;
    working.current = true; const current = startRequest();
    setError(null); setStep('analyzing'); setStage(0);
    try {
      const selected = photos.filter(Boolean);
      if (selected.reduce((sum, file) => sum + file.size, 0) > MAX_UPLOAD_TOTAL) throw new Error('Combined photos exceed the 12 MB request limit. Remove or resize a photo.');
      for (const file of selected) await validatePackagingFile(file);
      if (current.id !== request.current.id) return;
      setStage(1);
      const data = await analyzePackage(selected, { signal: current.controller.signal, fields: manualFields });
      if (current.id !== request.current.id) return;
      setStage(3); installResult(data);
    } catch (problem) {
      if (current.id !== request.current.id || cancelled(problem)) return;
      setError(problem); setStep('upload');
    } finally { if (current.id === request.current.id) working.current = false; }
  }
  async function updateAssessment() {
    if (working.current || !result) return;
    retryAction.current = updateAssessment;
    const changes = Object.fromEntries(Object.entries(fields).filter(([key, value]) => (value || null) !== (result.extracted[key] || null)).map(([key, value]) => [key, value.trim?.() || null]));
    if (!Object.keys(changes).length) return;
    working.current = true; const current = startRequest(); setUpdating(true); setError(null);
    try {
      const data = await reanalyzeVerification(result.verification_id, changes, { signal: current.controller.signal });
      if (current.id === request.current.id) installResult(data);
    } catch (problem) { if (current.id === request.current.id && !cancelled(problem)) setError(problem); }
    finally { if (current.id === request.current.id) { setUpdating(false); working.current = false; } }
  }
  async function openRecent(id) {
    if (working.current) return;
    retryAction.current = () => openRecent(id);
    working.current = true; const current = startRequest(); setOpening(id); setError(null);
    try { const data = await getVerification(id, { signal: current.controller.signal }); if (current.id === request.current.id) installResult(data); }
    catch (problem) { if (current.id === request.current.id && !cancelled(problem)) setError(problem); }
    finally { if (current.id === request.current.id) { setOpening(null); working.current = false; } }
  }
  function editPhotos(clear = false) {
    cancelAnalysis(); setStep('upload');
    if (clear) { setPhotos([null, null, null]); setManualFields({}); setResult(null); setFields({}); }
    uploadRef.current?.scrollIntoView?.({ block: 'start', behavior: 'instant' });
  }
  const totalSize = photos.filter(Boolean).reduce((sum, file) => sum + file.size, 0);
  const canAnalyze = Boolean(photos[0]) && totalSize <= MAX_UPLOAD_TOTAL && !opening;

  return <div className="min-w-0 space-y-6 pb-28 lg:pb-0">
    <header className="flex items-start gap-3"><div className="hidden rounded-2xl bg-teal-100 p-3 text-teal-800 sm:block"><ShieldCheck size={28} aria-hidden="true" /></div><div><p className="mb-1 text-xs font-bold tracking-wider text-teal-700 uppercase">Medicine Packaging Check</p><h1 className="text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl">Check if your medicine looks authentic</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">Analyze medicine packaging for suspicious names, label inconsistencies and other visual warning signs.</p></div></header>
    <ol aria-label="Packaging check steps" className="grid grid-cols-3 gap-2 rounded-2xl border border-slate-200 bg-white p-3 sm:p-4">{['Take photos', 'Analyze packaging', 'Review the risk assessment'].map((label, index) => <li key={label} className={`flex flex-col items-center gap-2 text-center text-xs font-semibold sm:flex-row sm:text-left ${step === 'upload' && index === 0 || step === 'analyzing' && index === 1 || step === 'result' && index === 2 ? 'text-teal-800' : 'text-slate-500'}`} aria-current={step === 'upload' && index === 0 || step === 'analyzing' && index === 1 || step === 'result' && index === 2 ? 'step' : undefined}><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-50 text-teal-800">{index + 1}</span>{label}</li>)}</ol>
    {error && <div className="space-y-2"><ErrorMessage title="Could not complete the packaging check" error={error} message={error.message || 'Please try again with clear photos.'} onRetry={() => retryAction.current?.()} /><button type="button" onClick={() => editPhotos(true)} className="button-secondary">Use Different Photos</button></div>}
    {step === 'upload' && <div ref={uploadRef} className="space-y-5 scroll-mt-24">
      <div className="flex flex-wrap items-end justify-between gap-2"><h2 className="text-lg font-bold text-slate-900">Photograph your packaging</h2><p className="text-xs text-slate-500">PNG or JPEG · 5 MB per photo · 12 MB total request</p></div>
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 p-3 backdrop-blur lg:static lg:rounded-2xl lg:border lg:p-4"><div className="mx-auto flex max-w-6xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs leading-5 text-slate-500">{!photos[0] ? 'Add the required front photo to enable analysis.' : 'Photos are processed in memory. Raw images are not saved.'}</p><button type="button" disabled={!canAnalyze} onClick={runAnalysis} className="flex min-h-12 items-center justify-center gap-2 rounded-xl bg-teal-800 px-6 text-sm font-bold text-white hover:bg-teal-900 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"><Sparkles size={18} aria-hidden="true" />Analyze packaging</button></div></div>
      <div className="grid gap-4 md:grid-cols-3">{slots.map((slot, index) => <PackagingUploadCard key={slot.id} {...slot} file={photos[index]} onChange={(file) => { setPhotos((previous) => previous.map((value, i) => i === index ? file : value)); setError(null); }} />)}</div>
      {totalSize > MAX_UPLOAD_TOTAL && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-sm text-rose-800">Combined photos exceed the 12 MB request limit. Remove or resize a photo.</p>}
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <div className="space-y-3"><div className="rounded-xl border border-teal-100 bg-teal-50 p-4"><h2 className="text-sm font-semibold text-teal-900">Internet product lookup</h2><p className="mt-2 text-xs leading-5 text-teal-800">After reading the label, we search DRAP?s online product index for matching details and show the source. Medicine-detail corrections are kept separate from internet findings.</p></div>
        <details className="group rounded-xl border border-slate-200 bg-white p-4"><summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 text-sm font-semibold text-slate-800">Correct the medicine details<ChevronDown size={17} className="group-open:rotate-180" aria-hidden="true" /></summary><p className="mb-3 text-xs leading-5 text-slate-500">Optional: enter details you can read clearly. Leave fields untouched to use the image reading.</p><div className="space-y-3">{Object.entries(correctionLabels).map(([key, label]) => <div key={key}><label htmlFor={`manual-${key}`} className="mb-1 block text-xs font-semibold text-slate-700">{label}</label><input id={`manual-${key}`} value={manualFields[key] ?? ''} maxLength={key === 'registration_number' ? 80 : key === 'manufacturer' ? 250 : 200} onChange={(event) => setManualFields((current) => ({ ...current, [key]: event.target.value }))} className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" /></div>)}</div></details></div>
        <aside aria-labelledby="photo-tips-title" className="rounded-2xl border border-teal-100 bg-teal-50 p-5"><h2 id="photo-tips-title" className="flex items-center gap-2 text-sm font-bold text-teal-900"><Lightbulb size={18} aria-hidden="true" />A clearer photo makes a better check</h2><ul className="mt-3 space-y-2 text-xs leading-6 text-teal-900"><li>Use even lighting; avoid flash reflections and glare.</li><li>Hold the camera steady and tap the label to focus.</li><li>Include the whole front of the pack and all printed edges.</li><li>Keep the name, ingredients and manufacturer legible.</li><li>Add the back or side to check agreement across the pack.</li></ul></aside>
      </div>
    </div>}
    {step === 'analyzing' && <section aria-labelledby="processing-title" aria-busy="true" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7"><div className="flex items-center gap-3"><LoaderCircle size={26} className="animate-spin text-teal-700 motion-reduce:animate-none" aria-hidden="true" /><h2 id="processing-title" className="text-lg font-bold text-slate-900">Analyzing your packaging</h2></div><p role="status" aria-live="polite" className="mt-3 text-sm text-slate-600">{processingStages[stage]}…</p><ol className="mt-5 space-y-3">{processingStages.map((label, index) => <li key={label} className={`flex items-center gap-2 text-xs ${index <= stage ? 'font-semibold text-teal-800' : 'text-slate-400'}`}>{index < stage ? <CheckCircle2 size={16} aria-hidden="true" /> : <span className="flex h-4 w-4 items-center justify-center rounded-full border text-[10px]">{index + 1}</span>}{label}{index > stage && <span className="sr-only">pending</span>}</li>)}</ol><p className="mt-4 text-xs leading-5 text-slate-500">Text reading and visual inspection share one AI request. A live DRAP product search finds online references without using another AI request; local catalog comparisons remain available.</p><div aria-hidden="true" className="mt-6 grid gap-3 sm:grid-cols-2"><div className="h-24 animate-pulse rounded-xl bg-slate-100 motion-reduce:animate-none" /><div className="h-24 animate-pulse rounded-xl bg-slate-100 motion-reduce:animate-none" /></div><button type="button" onClick={cancelAnalysis} className="button-secondary mt-5">Cancel analysis</button><p className="mt-2 text-xs text-slate-500">Cancel closes your request. An AI request already sent may still finish on the server.</p></section>}
    {step === 'result' && result && <div ref={resultRef} tabIndex={-1} className="scroll-mt-24 focus-visible:outline-offset-4"><PackagingResults result={result} fields={fields} setFields={setFields} updating={updating} onUpdate={updateAssessment} onReport={() => navigate(`/reporting?verification_id=${result.verification_id}`)} onEditPhotos={() => editPhotos()} onNew={() => editPhotos(true)} /></div>}
    {opening && <p role="status" aria-live="polite" className="text-sm text-teal-800">Opening recent check…</p>}
    {history.length > 0 && <details className="rounded-2xl border border-slate-200 bg-white p-4"><summary className="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-bold text-slate-800"><Clock3 size={17} aria-hidden="true" />Recent checks ({history.length})</summary><ul className="mt-2 divide-y divide-slate-100">{history.map((item) => <li key={item.verification_id}><button type="button" disabled={step === 'analyzing' || updating || Boolean(opening)} onClick={() => openRecent(item.verification_id)} className="flex min-h-16 w-full items-center justify-between gap-3 py-3 text-left disabled:opacity-50"><span className="min-w-0"><span className="block truncate text-sm font-semibold text-slate-900">{item.brand_name || 'Unreadable product'} · #{item.verification_id}</span><span className="mt-1 block text-xs text-slate-500">{item.status_label}</span>{item.simulated && <span className="mt-1 inline-block"><DemoBadge /></span>}</span><ArrowRight size={16} className="shrink-0 text-teal-700" aria-hidden="true" /></button></li>)}</ul></details>}
    {historyError && <p className="text-xs text-slate-500">Recent checks could not be loaded. You can still analyze new photos.</p>}
  </div>;
}
