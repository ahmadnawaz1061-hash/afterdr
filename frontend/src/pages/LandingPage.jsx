import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowRight, Inbox, Pill } from 'lucide-react';
import { Link } from 'react-router-dom';
import LoadingState from '../components/common/LoadingState';
import ErrorMessage from '../components/common/ErrorMessage';
import { DemoBadge, DraftBadge } from '../components/common/StatusBadge';
import { navigation } from '../components/layout/navigation';
import { substitutionNotice } from '../components/medicine/medicineDetails';
import { searchMedicine, USE_MOCKS } from '../services/api';
import { useAuth } from '../auth/AuthContext';

const featureDescriptions = {
  '/prescription': 'Upload a prescription and review the extracted instructions before confirming them.',
  '/scheduler': 'Choose reminder times and keep track of doses throughout your day.',
  '/alternatives': 'Compare candidate medicines using their documented ingredients and formulation.',
  '/verification': 'Compare packaging details with available records and see what needs a closer look.',
  '/reporting': 'Organize findings and purchase details into a complaint draft for your review.',
};

export default function LandingPage() {
  const { user } = useAuth();
  const [preview, setPreview] = useState({ status: 'empty', medicines: null });
  const requestId = useRef(0);

  // Ignore responses after leaving the page or starting a newer request.
  useEffect(() => () => { requestId.current += 1; }, []);

  async function loadPreview() {
    const currentRequest = ++requestId.current;
    setPreview({ status: 'loading', medicines: null });
    try {
      const medicines = await searchMedicine('');
      if (!Array.isArray(medicines) || medicines.some((medicine) => !medicine || typeof medicine.brand_name !== 'string')) {
        throw new Error('Invalid medicine catalog response');
      }
      if (currentRequest !== requestId.current) return;
      setPreview({ status: medicines.length ? 'success' : 'empty', medicines });
    } catch {
      if (currentRequest === requestId.current) setPreview({ status: 'error', medicines: null });
    }
  }

  return (
    <div className="space-y-12 sm:space-y-16">
      <section aria-labelledby="landing-title" className="grid overflow-hidden rounded-3xl border border-teal-900 bg-teal-900 text-white xl:grid-cols-[1.4fr_1fr]">
        <div className="p-6 sm:p-10 lg:p-12">
          <p className="text-xs font-semibold tracking-[0.18em] text-teal-200 uppercase">Care beyond the consultation</p>
          <h1 id="landing-title" className="mt-5 max-w-xl text-4xl font-bold leading-tight tracking-tight sm:text-5xl">Your next step,<br />a little clearer.</h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-teal-50">Bring prescription instructions, medicine schedules, and package reviews together. After Dr helps you organize the everyday steps after your consultation.</p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Link to={user ? '/dashboard' : '/register'} className="inline-flex min-h-12 items-center justify-center gap-3 rounded-xl bg-white px-6 py-3 text-sm font-bold text-teal-900 hover:bg-teal-50 focus-visible:outline-white">{user ? 'Open your dashboard' : 'Create your account'} <ArrowRight size={18} aria-hidden="true" /></Link>
            <a href="#landing-features" className="inline-flex min-h-12 items-center gap-2 rounded-lg px-2 py-3 text-sm font-semibold text-white hover:underline focus-visible:outline-white">Explore the five tools <ArrowDown size={16} aria-hidden="true" /></a>
          </div>
          <p className="mt-6 text-xs leading-5 text-teal-200">Review medicine decisions with your pharmacist or prescriber.</p>
        </div>
        <div className="flex flex-col justify-center border-t border-teal-700 bg-teal-800 p-6 sm:p-10 xl:border-t-0 xl:border-l">
          <h2 className="text-lg font-semibold">A little structure for your next step</h2>
          <ol className="mt-6 space-y-6">
            {[
              ['Start with your prescription', 'Keep the instructions from your consultation together.'],
              ['Review the details', 'Check extracted information and clarify anything uncertain.'],
              ['Plan your routine', 'Organize confirmed instructions and questions for your care team.'],
            ].map(([title, description], index) => <li key={title} className="flex gap-4">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-teal-700 text-sm font-semibold text-white" aria-hidden="true">{index + 1}</span>
              <div><h3 className="text-sm font-semibold">{title}</h3><p className="mt-1 text-sm leading-6 text-teal-100">{description}</p></div>
            </li>)}
          </ol>
        </div>
      </section>

      <section id="landing-features" tabIndex={-1} aria-labelledby="features-title" className="rounded-xl">
        <div className="mb-6 max-w-2xl">
          <p className="text-xs font-bold tracking-[0.18em] text-teal-700 uppercase">Five connected tools</p>
          <h2 id="features-title" className="mt-3 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Support for each part of your medicine journey.</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">Start where you need support, with room to review the details at every step.</p>
        </div>
        <ul className="divide-y divide-slate-200 overflow-hidden rounded-2xl border border-slate-200 bg-white">
          {navigation.slice(2).map(({ to, label, icon: Icon }, index) => <li key={to} className="p-5 sm:p-6">
            <Link to={to} aria-labelledby={`feature-${index}`} className="group flex items-start gap-4 rounded-lg sm:items-center sm:gap-5">
              <span className="rounded-xl bg-teal-50 p-3 text-teal-700"><Icon size={24} aria-hidden="true" /></span>
              <div className="min-w-0 flex-1 sm:grid sm:grid-cols-[1fr_1.5fr] sm:items-center sm:gap-6">
                <h3 id={`feature-${index}`} className="text-base font-semibold text-slate-900 group-hover:text-teal-800">{label}</h3>
                <p className="mt-1 text-sm leading-6 text-slate-600 sm:mt-0">{featureDescriptions[to]}</p>
              </div>
              <ArrowRight size={18} className="mt-3 shrink-0 text-slate-400 group-hover:text-teal-700 sm:mt-0" aria-hidden="true" />
            </Link>
            {to === '/alternatives' && <p className="mt-4 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-950">{substitutionNotice}</p>}
            {to === '/reporting' && <div className="mt-4"><DraftBadge /></div>}
          </li>)}
        </ul>
      </section>

      <section aria-labelledby="catalog-preview-title" className="grid gap-6 lg:grid-cols-[1fr_1.3fr] lg:gap-10">
        <div>
          <p className="text-xs font-bold tracking-[0.18em] text-teal-700 uppercase">A look inside</p>
          <h2 id="catalog-preview-title" className="mt-3 text-2xl font-bold tracking-tight text-slate-900">Clear details. Room to review.</h2>
          <p className="mt-3 text-sm leading-7 text-slate-600">Explore a few entries from the medicine catalog to see how product information is organized.</p>
          <p className="mt-4 text-sm leading-6 text-slate-600">No prescription upload is needed to explore the catalog.</p>
        </div>
        <div className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <h3 className="font-semibold text-slate-900">Medicine catalog preview</h3>
          {USE_MOCKS && <div className="mt-3"><DemoBadge /></div>}
          {preview.status === 'loading' && <LoadingState title="Loading the catalog…" message="Gathering medicine details for your preview." />}
          {preview.status === 'error' && <ErrorMessage title="The catalog could not be loaded" message="Please try again. You can still explore the five tools above." />}
          {preview.status === 'empty' && <div className="state-panel">
            <Inbox size={30} className="mx-auto mb-3 text-slate-400" aria-hidden="true" />
            <p role="status" aria-live="polite" className="text-sm text-slate-600">{preview.medicines === null ? 'Ready when you are. Load the catalog to take a look.' : 'No medicines are available to preview yet.'}</p>
          </div>}
          {preview.status === 'success' && <>
            <p role="status" aria-live="polite" className="mt-3 text-sm text-slate-600">Showing {Math.min(preview.medicines.length, 3)} {preview.medicines.length === 1 ? 'catalog entry' : 'catalog entries'}.</p>
            <ul className="mt-4 divide-y divide-slate-200">
              {preview.medicines.slice(0, 3).map((medicine, index) => <li key={medicine.id ?? index} className="flex items-start gap-3 py-4">
                <Pill size={20} className="mt-1 shrink-0 text-teal-700" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <h4 className="font-semibold text-slate-900 wrap-anywhere">{medicine.brand_name}</h4>
                  <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-600 wrap-anywhere">
                    <div><dt className="text-xs text-slate-500">Strength</dt><dd>{medicine.strength || 'Not provided'}</dd></div>
                    <div><dt className="text-xs text-slate-500">Form</dt><dd>{medicine.dosage_form || 'Not provided'}</dd></div>
                  </dl>
                  {(USE_MOCKS || medicine.is_demo || medicine.data_source === 'demo_dataset') && <div className="mt-3"><DemoBadge /></div>}
                </div>
              </li>)}
            </ul>
          </>}
          <button type="button" aria-disabled={preview.status === 'loading'}
            onClick={() => { if (preview.status !== 'loading') loadPreview(); }}
            className="button-secondary mt-5 w-full aria-disabled:cursor-wait aria-disabled:bg-slate-100 sm:w-auto">
            {preview.status === 'loading' ? 'Loading catalog…' : preview.status === 'error' ? 'Try again' : preview.medicines === null ? 'Load catalog preview' : 'Refresh catalog'}
          </button>
        </div>
      </section>
    </div>
  );
}
