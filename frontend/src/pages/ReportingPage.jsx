import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Download, FilePenLine } from 'lucide-react';
import { getVerification, createReportDraft, downloadReportDraft } from '../services/api';
import { DemoBadge, DraftBadge } from '../components/common/StatusBadge';
import ErrorMessage from '../components/common/ErrorMessage';
import { extractedLabels } from '../components/verification/PackagingResults';

export default function ReportingPage() {
  const [params] = useSearchParams();
  const id = params.get('verification_id');
  const [assessment, setAssessment] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState(null);
  const [form, setForm] = useState({ pharmacy_name: '', purchase_date: '', description: '' });
  const request = useRef(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; request.current?.abort(); }; }, []);
  useEffect(() => {
    if (!id || !/^\d+$/.test(id) || Number(id) < 1) { setAssessment(null); setLoading(false); setError(id ? new Error('Choose a valid packaging check before preparing a draft.') : null); return; }
    const controller = new AbortController(); setAssessment(null); setLoading(true); setError(null); setDraft(null);
    getVerification(id, { signal: controller.signal }).then((data) => { if (controller.signal.aborted) return; setAssessment(data); setForm((old) => ({ ...old, description: data.signals.filter((s) => ['high', 'medium'].includes(s.severity)).map((s) => `${s.title}: ${s.detail}`).join('\n') })); }).catch((problem) => { if (!controller.signal.aborted) setError(problem); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, reload]);
  function updateField(key, value) {
    setForm((previous) => ({ ...previous, [key]: value }));
    setDraft(null);
  }
  async function save(event) {
    event?.preventDefault(); if (saving || !assessment) return;
    request.current = new AbortController(); setSaving(true); setError(null);
    try {
      const response = await createReportDraft({ verification_id: assessment.verification_id, ...form, purchase_date: form.purchase_date || null }, { signal: request.current.signal });
      if (mounted.current) setDraft(response);
    } catch (problem) { if (mounted.current && problem.name !== 'CanceledError') setError(problem); }
    finally { if (mounted.current) setSaving(false); }
  }
  async function download() {
    if (!draft || saving) return;
    setSaving(true); setError(null);
    try {
      const blob = await downloadReportDraft(draft.report_id); const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = `after-dr-report-${draft.report_id}-draft.pdf`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (problem) { if (mounted.current) setError(problem); }
    finally { if (mounted.current) setSaving(false); }
  }
  return <div className="space-y-5"><header><p className="mb-2 text-xs font-bold tracking-wider text-teal-700 uppercase">Packaging concern report</p><h1 className="flex items-center gap-3 text-2xl font-bold text-slate-950"><FilePenLine size={26} className="text-teal-700" aria-hidden="true" />Prepare a report draft</h1><p className="mt-2 text-sm leading-6 text-slate-600">Bring assessment evidence and purchase details together for your review.</p></header><DraftBadge /><p className="text-xs leading-5 text-slate-500">Saving creates a downloadable draft. No report is sent to DRAP or any other recipient.</p>
    {loading && <p role="status" aria-live="polite" className="text-sm text-teal-800">Loading packaging assessment…</p>}
    {error && <ErrorMessage title="Could not prepare the draft" error={error} message={error.message} onRetry={() => draft ? download() : assessment ? save() : setReload((value) => value + 1)} />}
    {!id && <section className="rounded-2xl border border-slate-200 bg-white p-6"><h2 className="text-lg font-bold text-slate-900">Start with a packaging check</h2><p className="mt-2 text-sm text-slate-600">Analyze packaging, then choose Prepare a report draft from its assessment.</p><Link to="/verification" className="button-secondary mt-4">Open Medicine Packaging Check</Link></section>}
    {assessment && <><section className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-bold text-slate-900">Assessment #{assessment.verification_id}</h2>{assessment.simulated && <DemoBadge />}</div><p className="mt-2 text-sm font-semibold text-slate-800">{assessment.status_label}</p><p className="mt-1 text-xs text-slate-500">Risk level: {assessment.risk_level}{assessment.risk_score !== null ? ` · Risk score: ${assessment.risk_score}/100` : ''}</p><p className="mt-3 text-sm leading-6 text-slate-600">{assessment.summary}</p><dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(extractedLabels).map(([key, label]) => <div key={key}><dt className="text-xs text-slate-500">{label}</dt><dd className="break-words text-sm font-medium text-slate-800">{assessment.extracted[key] || 'Not visible'}</dd></div>)}</dl><details className="mt-4 border-t border-slate-100 pt-2"><summary className="min-h-11 cursor-pointer py-3 text-sm font-semibold text-teal-800">Evidence and limitations included in the PDF</summary><ul className="space-y-2 text-xs leading-5 text-slate-600">{assessment.signals.map((signal, index) => <li key={index}><strong>{signal.title}</strong> ({signal.origin}): {signal.detail}</li>)}</ul>{assessment.matched_reference && <p className="mt-3 text-xs text-slate-600">Reference: {assessment.matched_reference.brand_name} · {assessment.matched_reference.data_source} · {assessment.matched_reference.comparison_status}</p>}<ul className="mt-3 space-y-2 text-xs leading-5 text-slate-500">{assessment.next_steps.map((step) => <li key={step}>{step}</li>)}{assessment.limitations.map((limit) => <li key={limit}>{limit}</li>)}</ul></details></section>
    <form onSubmit={save} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold text-slate-900">Purchase details and concerns</h2><div className="grid gap-4 sm:grid-cols-2"><div><label htmlFor="pharmacy" className="mb-1 block text-xs font-semibold text-slate-700">Seller or pharmacy</label><input id="pharmacy" required maxLength={200} value={form.pharmacy_name} onChange={(event) => updateField('pharmacy_name', event.target.value)} className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" /></div><div><label htmlFor="purchase-date" className="mb-1 block text-xs font-semibold text-slate-700">Purchase date (optional)</label><input id="purchase-date" type="date" value={form.purchase_date} onChange={(event) => updateField('purchase_date', event.target.value)} className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" /></div></div><div><label htmlFor="concerns" className="mb-1 block text-xs font-semibold text-slate-700">Observed concerns</label><textarea id="concerns" required rows={5} maxLength={5000} value={form.description} onChange={(event) => updateField('description', event.target.value)} className="w-full rounded-lg border border-slate-300 p-3 text-sm" /></div><button disabled={saving || !form.pharmacy_name.trim() || !form.description.trim()} className="min-h-11 rounded-xl bg-teal-800 px-5 text-sm font-semibold text-white disabled:bg-slate-300">{saving ? 'Preparing draft…' : 'Save report draft'}</button></form>
    {draft && <section role="status" className="rounded-2xl border border-teal-200 bg-teal-50 p-5"><p className="text-sm font-semibold text-teal-900">Draft #{draft.report_id} is ready for review.</p><button type="button" disabled={saving} onClick={download} className="button-secondary mt-3 gap-2"><Download size={17} aria-hidden="true" />Download draft PDF</button></section>}</>}
  </div>;
}
