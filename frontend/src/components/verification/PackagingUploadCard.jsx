import { useEffect, useRef, useState } from 'react';
import { Camera, ImagePlus, RefreshCw, X } from 'lucide-react';
import { validatePackagingFile } from './packagingUploads';

export default function PackagingUploadCard({ id, title, hint, requirement, file, onChange, disabled = false }) {
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef(null);
  const request = useRef(0);
  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file); setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => () => { request.current += 1; }, []);
  async function choose(candidate) {
    if (!candidate || disabled) return;
    const current = ++request.current; setError(''); setChecking(true);
    try {
      await validatePackagingFile(candidate);
      if (current === request.current) onChange(candidate);
    } catch (problem) { if (current === request.current) setError(problem.message); }
    finally { if (current === request.current) setChecking(false); }
  }
  return <section aria-labelledby={`${id}-title`} className={`min-w-0 rounded-2xl border bg-white p-4 transition-colors ${dragging ? 'border-teal-600 bg-teal-50' : 'border-slate-200'}`} onDragOver={(event) => { event.preventDefault(); if (!disabled) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); if (event.dataTransfer.files.length > 1) { setError('Choose one photo for this card.'); return; } choose(event.dataTransfer.files[0]); }}>
    <div className="flex flex-wrap items-start justify-between gap-2"><h3 id={`${id}-title`} className="text-sm font-bold text-slate-900">{title}</h3><span className="text-[11px] font-semibold text-teal-700">{requirement}</span></div>
    <p className="mt-1 min-h-10 text-xs leading-5 text-slate-500">{hint}</p>
    <label htmlFor={`${id}-file`} className="sr-only">{title} photograph</label>
    <input ref={input} id={`${id}-file`} type="file" accept="image/png,image/jpeg" className="sr-only" disabled={disabled} onChange={(event) => { choose(event.target.files?.[0]); event.target.value = ''; }} />
    {preview ? <div className="relative mt-3 overflow-hidden rounded-xl bg-slate-100"><img src={preview} alt={`${title} preview`} className="h-40 w-full object-contain" /><button type="button" disabled={disabled} onClick={() => { request.current += 1; onChange(null); setError(''); }} aria-label={`Remove ${title} photo`} className="icon-button absolute top-2 right-2 inline-flex"><X size={17} aria-hidden="true" /></button></div> : <button type="button" disabled={disabled || checking} onClick={() => input.current?.click()} className="mt-3 flex min-h-40 w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-3 py-6 text-slate-500 hover:border-teal-500 hover:bg-teal-50"><ImagePlus size={28} aria-hidden="true" /><span className="text-xs">Drop a photo here</span><span className="text-xs font-semibold text-teal-800">or choose a file</span></button>}
    {file && <p className="mt-2 truncate text-xs text-slate-500" title={file.name}>{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB</p>}
    <div className="mt-3 flex flex-wrap gap-2"><button type="button" disabled={disabled || checking} onClick={() => input.current?.click()} className="button-secondary flex-1 gap-1 px-3 text-xs">{file ? <RefreshCw size={14} aria-hidden="true" /> : <ImagePlus size={14} aria-hidden="true" />}{file ? 'Replace' : 'Choose File'}</button><label className={`button-secondary flex-1 gap-1 px-3 text-xs ${disabled ? 'pointer-events-none opacity-50' : 'cursor-pointer'}`}><Camera size={14} aria-hidden="true" />Camera<input type="file" accept="image/png,image/jpeg" capture="environment" disabled={disabled} className="sr-only" aria-label={`Take ${title} photo`} onChange={(event) => { choose(event.target.files?.[0]); event.target.value = ''; }} /></label></div>
    {checking && <p role="status" className="mt-2 text-xs text-teal-800">Validating image…</p>}
    {error && <p role="alert" className="mt-2 text-xs font-medium leading-5 text-rose-700">{error}</p>}
  </section>;
}
