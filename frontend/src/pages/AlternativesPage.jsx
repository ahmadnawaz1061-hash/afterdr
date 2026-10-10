import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, ChevronDown, Pill, Search, ShieldAlert } from 'lucide-react';
import ErrorMessage from '../components/common/ErrorMessage';
import { getMedicineAlternatives, searchAlternativeMedicines } from '../services/alternativesApi';

const NOTICE = 'Confirm with your pharmacist or prescriber before substituting.';
const attributes = [
  ['active_ingredient', 'Active ingredient(s)'], ['strength', 'Strength'],
  ['dosage_form', 'Dosage form'], ['route', 'Route'], ['release_type', 'Release type'],
];
const valueLabel = (value) => !value?.trim() || value.trim().toLowerCase() === 'unknown' ? 'Not documented' : value;
const emptySearch = { status: 'idle', records: [], term: '', error: null, hasMore: false, moreStatus: 'idle', moreError: null };
const emptyComparison = { status: 'idle', records: [], error: null };

function Source({ medicine }) {
  const safeLink = (url) => {
    try {
      const parsed = new URL(url);
      return parsed.protocol === 'https:' && !parsed.username && !parsed.password && (
        parsed.hostname === 'dra.gov.pk' || parsed.hostname.endsWith('.dra.gov.pk') ||
        (parsed.hostname === 'getzpharma.com' && parsed.pathname === '/wp-content/uploads/2023/03/Getzid-MR-Range-Leaflet-PAK.pdf')
      );
    } catch { return false; }
  };
  return <div className="space-y-1 text-xs leading-5 text-slate-600">
    <p>DRAP Pakistan &middot; Registration {medicine.registration_no}</p>
    <p>{safeLink(medicine.source_url) && <a href={medicine.source_url} target="_blank" rel="noreferrer" className="font-medium text-teal-800 underline underline-offset-4">View DRAP listing (opens a new tab)</a>}{medicine.source_checked_at && <span className="ml-2">Checked {medicine.source_checked_at}</span>}</p>
    {medicine.source_search_query && <p>On the DRAP page, search registration {medicine.registration_no} to find this product.</p>}
    {safeLink(medicine.formulation_source_url) && <a href={medicine.formulation_source_url} target="_blank" rel="noreferrer" className="block font-medium text-teal-800 underline underline-offset-4">View formulation evidence (opens a new tab)</a>}
  </div>;
}

function Disclosure({ label, children }) {
  return <details className="group mt-3 border-t border-slate-200 pt-1">
    <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-teal-800 [&::-webkit-details-marker]:hidden">
      {label}<ChevronDown size={16} className="shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
    </summary>
    <div className="space-y-3 pb-2 pt-1">{children}</div>
  </details>;
}

function CatalogDetails({ medicine }) {
  return <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
    {attributes.map(([key, label]) => <div key={key} className="min-w-0"><dt className="text-xs text-slate-500">{label}</dt><dd className="break-words font-medium text-slate-800">{valueLabel(medicine[key])}</dd></div>)}
    <div className="min-w-0"><dt className="text-xs text-slate-500">Manufacturer</dt><dd className="break-words text-slate-800">{valueLabel(medicine.manufacturer)}</dd></div>
  </dl>;
}

function CompactLoading({ children }) {
  return <p role="status" className="flex items-center gap-2 py-5 text-sm text-slate-600"><span aria-hidden="true" className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-slate-200 border-t-teal-700 motion-reduce:animate-none" />{children}</p>;
}

function Candidate({ medicine, original }) {
  return <article aria-labelledby={`candidate-${medicine.id}`} className="min-w-0 rounded-xl border border-teal-200 bg-white p-4">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0 flex-[1_1_7rem]"><p className="text-[11px] font-semibold tracking-wider text-teal-700 uppercase">Potential alternative</p><h3 id={`candidate-${medicine.id}`} className="mt-1 break-words text-xl font-semibold text-slate-900">{medicine.brand_name}</h3></div>
      <span className="max-w-full rounded-lg bg-teal-50 px-3 py-1.5 text-sm font-semibold break-words text-teal-900">{valueLabel(medicine.strength)}</span>
    </div>
    <p className="mt-2 break-words text-sm font-medium text-slate-800">{valueLabel(medicine.active_ingredient)}</p>
    <p className="mt-1 break-words text-xs leading-5 text-slate-600">{[medicine.dosage_form, medicine.route, medicine.release_type].map(valueLabel).join(' \u00b7 ')}</p>
    <p className="mt-1 break-words text-xs leading-5 text-slate-500">{valueLabel(medicine.manufacturer)}</p>
    <p className="mt-3 flex items-start gap-2 rounded-lg bg-teal-50 px-3 py-2 text-xs font-medium leading-5 text-teal-900"><CheckCircle2 size={15} className="mt-0.5 shrink-0" aria-hidden="true" />All 5 catalog attributes match.</p>
    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-950">
      <p className="font-semibold">{NOTICE}</p><p>This comparison is for information only. Clinical interchangeability is not established. Do not change or stop treatment without professional approval.</p>
    </div>
    <Disclosure label="Comparison details & source">
      <ul className="flex flex-wrap gap-x-4 gap-y-1">{medicine.match_reasons.map((reason, index) => <li key={`${reason}-${index}`} className="flex items-start gap-1 text-xs leading-5 text-teal-900"><CheckCircle2 size={13} className="mt-1 shrink-0" aria-hidden="true" />{reason}</li>)}</ul>
      <div className="overflow-x-auto rounded-lg border border-slate-200" role="region" aria-label={`Attribute comparison for ${medicine.brand_name}`} tabIndex={0}>
        <table className="w-full text-left text-xs">
          <caption className="sr-only">Catalog attributes for the selected medicine and {medicine.brand_name}. Strengths may use different equivalent units.</caption>
          <thead className="bg-slate-50 text-slate-600"><tr><th scope="col" className="p-2">Attribute</th><th scope="col" className="p-2">Selected medicine</th><th scope="col" className="p-2">Potential alternative</th></tr></thead>
          <tbody>{attributes.map(([key, label]) => <tr key={key} className="border-t border-slate-200"><th scope="row" className="p-2 font-medium text-slate-700">{label}</th><td className="p-2 break-words text-slate-600">{valueLabel(original[key])}</td><td className="p-2 break-words font-medium text-slate-900">{valueLabel(medicine[key])}</td></tr>)}</tbody>
        </table>
      </div>
      <Source medicine={medicine} />
    </Disclosure>
  </article>;
}

export default function AlternativesPage() {
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState(emptySearch);
  const [original, setOriginal] = useState(null);
  const [comparison, setComparison] = useState(emptyComparison);
  const searchRequest = useRef({ id: 0, controller: null });
  const comparisonRequest = useRef({ id: 0, controller: null });
  const comparisonRef = useRef(null);
  const resultsRef = useRef(null);
  function cancel(request) { request.current.id += 1; request.current.controller?.abort(); }
  useEffect(() => () => { cancel(searchRequest); cancel(comparisonRequest); }, []);

  useEffect(() => {
    if (original && comparison.status === 'loading') {
      comparisonRef.current?.focus({ preventScroll: true });
    }
    if (original && document.activeElement === comparisonRef.current) {
      const desktop = window.matchMedia?.('(min-width: 1024px)').matches;
      comparisonRef.current?.scrollIntoView?.({ block: desktop ? 'nearest' : 'start', behavior: 'instant' });
    }
  }, [original, comparison.status]);

  function returnToResults() {
    resultsRef.current?.focus({ preventScroll: true });
    resultsRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'instant' });
  }

  function resetResults() {
    cancel(searchRequest); cancel(comparisonRequest);
    setSearch(emptySearch); setOriginal(null); setComparison(emptyComparison);
  }

  async function runSearch(term = query) {
    if (search.status === 'loading' && term.trim() === search.term) return;
    cancel(searchRequest); cancel(comparisonRequest);
    const id = searchRequest.current.id;
    const controller = new AbortController();
    searchRequest.current.controller = controller;
    setOriginal(null); setComparison(emptyComparison);
    setSearch({ ...emptySearch, status: 'loading', term: term.trim() });
    try {
      const records = await searchAlternativeMedicines(term, { signal: controller.signal });
      if (id !== searchRequest.current.id) return;
      setSearch({ ...emptySearch, status: records.length ? 'success' : 'empty', records, term: term.trim(), hasMore: records.length === 10 });
    } catch (error) {
      if (id !== searchRequest.current.id) return;
      setSearch({ ...emptySearch, status: 'error', term: term.trim(), error });
    }
  }

  async function loadMore() {
    if (!search.hasMore || search.moreStatus === 'loading') return;
    cancel(searchRequest);
    const id = searchRequest.current.id;
    const controller = new AbortController();
    searchRequest.current.controller = controller;
    setSearch((previous) => ({ ...previous, moreStatus: 'loading', moreError: null }));
    try {
      const records = await searchAlternativeMedicines(search.term, { signal: controller.signal, offset: search.records.length });
      if (id !== searchRequest.current.id) return;
      setSearch((previous) => ({ ...previous, records: [...previous.records, ...records], hasMore: records.length === 10, moreStatus: 'idle' }));
    } catch (error) {
      if (id !== searchRequest.current.id) return;
      setSearch((previous) => ({ ...previous, moreStatus: 'error', moreError: error }));
    }
  }

  async function selectMedicine(medicine) {
    if (original?.id === medicine.id && comparison.status === 'loading') return;
    cancel(comparisonRequest);
    const id = comparisonRequest.current.id;
    const controller = new AbortController();
    comparisonRequest.current.controller = controller;
    setOriginal(medicine); setComparison({ status: 'loading', records: [], error: null });
    try {
      const records = await getMedicineAlternatives(medicine.id, { signal: controller.signal });
      if (id !== comparisonRequest.current.id) return;
      setComparison({ status: records.length ? 'success' : 'empty', records, error: null });
    } catch (error) {
      if (id !== comparisonRequest.current.id) return;
      setComparison({ status: 'error', records: [], error });
    }
  }

  return <div className="space-y-4">
    <header className="flex items-start gap-3">
      <div className="hidden rounded-xl bg-teal-100 p-3 text-teal-800 sm:block"><Pill size={24} aria-hidden="true" /></div>
      <div><h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Alternative medicine finder</h1><p className="mt-1 text-sm leading-6 text-slate-600">Choose your exact medicine to compare Pakistan catalog alternatives.</p></div>
    </header>
    <aside aria-label="Substitution guidance" className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs leading-5 text-amber-950"><ShieldAlert size={17} className="mt-0.5 shrink-0" aria-hidden="true" /><p>{NOTICE} Allergies and treatment history need professional review.</p></aside>
    <section aria-labelledby="search-title" className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5">
      <h2 id="search-title" className="text-sm font-semibold text-slate-900">1. Find your prescribed medicine</h2>
      <form onSubmit={(event) => { event.preventDefault(); runSearch(); }} className="mt-3">
        <label htmlFor="alternative-search" className="sr-only">Brand or active ingredient</label>
        <div className="flex flex-wrap gap-2">
          <div className="relative min-w-0 flex-[1_1_14rem]"><Search size={18} className="pointer-events-none absolute top-3.5 left-3 text-slate-400" aria-hidden="true" /><input id="alternative-search" type="search" maxLength={100} value={query} onChange={(event) => { setQuery(event.target.value); resetResults(); }} placeholder="Brand or ingredient, e.g. Panadol" aria-describedby="search-hint" className="min-h-11 w-full rounded-xl border border-slate-400 bg-white py-2.5 pr-3 pl-10 text-sm text-slate-900" /></div>
          <button disabled={!query.trim() || search.status === 'loading'} className="min-h-11 flex-1 rounded-xl bg-teal-800 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-900 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 sm:flex-none">Search medicines</button>
          <button type="button" disabled={search.status === 'loading'} onClick={() => { setQuery(''); runSearch(''); }} className="button-secondary flex-1 disabled:cursor-not-allowed disabled:opacity-60 sm:flex-none">Browse catalog</button>
        </div>
        <p id="search-hint" className="mt-2 text-xs leading-5 text-slate-500">Search by brand or ingredient; small spelling mistakes are supported. Match the strength and form on your prescription. DRAP snapshot; current registration and stock are not verified.</p>
      </form>
    </section>
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.3fr)]">
      <section ref={resultsRef} tabIndex={-1} aria-labelledby="results-title" className="min-w-0 rounded-2xl border border-slate-200 bg-white focus-visible:outline-offset-[-3px]">
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3"><h2 id="results-title" className="text-sm font-semibold text-slate-900">Catalog results</h2>{search.status === 'success' && <span role="status" className="text-xs text-slate-500">{search.records.length} shown{search.hasMore ? ' \u00b7 more available' : ''}</span>}</div>
        {search.status === 'idle' && <div className="px-4 py-8 text-center"><Search size={24} className="mx-auto mb-3 text-slate-300" aria-hidden="true" /><p className="text-sm text-slate-600">Search a name or browse the catalog.</p><p className="mt-1 text-xs text-slate-500">Select a product to see its alternatives.</p></div>}
        {search.status === 'loading' && <div className="px-4"><CompactLoading>Searching the catalog...</CompactLoading></div>}
        {search.status === 'error' && <div className="px-4 pb-4"><ErrorMessage title="Could not search medicines" error={search.error} message={search.error?.response?.status === 401 ? 'Your session has expired. Sign in again to use the catalog.' : search.error?.message || 'Check your connection and try again.'} onRetry={() => runSearch(search.term)} /></div>}
        {search.status === 'empty' && <div className="px-4 py-6" role="status"><h3 className="text-sm font-semibold text-slate-900">No catalog records found</h3><p className="mt-2 text-xs leading-5 text-slate-600">{search.term ? 'Check the spelling or try the active ingredient. A missing record does not mean the medicine is unregistered.' : 'No Pakistan catalog records are available yet. Ask your project team to load the documented DRAP catalog.'}</p></div>}
        {search.status === 'success' && search.records.some((medicine) => medicine.similar_spelling) && <p role="status" className="border-b border-amber-100 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-950">Showing similar spellings for “{search.term}”. Check the medicine name, strength and form before selecting.</p>}
        {search.status === 'success' && <div role="region" aria-label="Scrollable medicine results" tabIndex={0} className="max-h-72 overflow-y-auto overscroll-contain focus-visible:outline-offset-[-3px] lg:max-h-[26rem]">
          <ul className="divide-y divide-slate-100">{search.records.map((medicine) => <li key={medicine.id}>
            <button type="button" aria-pressed={original?.id === medicine.id} onClick={() => selectMedicine(medicine)} disabled={original?.id === medicine.id && comparison.status === 'loading'} aria-label={`Compare alternatives for ${medicine.brand_name}`} className={`flex min-h-20 w-full items-center gap-3 px-4 py-3 text-left transition-colors focus-visible:outline-offset-[-3px] disabled:cursor-wait ${original?.id === medicine.id ? 'border-l-[3px] border-teal-700 bg-teal-50' : 'border-l-[3px] border-transparent hover:bg-slate-50'}`}>
              <span className="min-w-0 flex-1"><span className="block break-words text-sm font-semibold text-slate-900">{medicine.brand_name}</span><span className="mt-0.5 block break-words text-xs leading-5 text-slate-600">{valueLabel(medicine.active_ingredient)} &middot; {valueLabel(medicine.strength)}</span><span className="block break-words text-[11px] leading-5 text-slate-500">{valueLabel(medicine.dosage_form)} &middot; Reg. {medicine.registration_no}</span></span>
              {original?.id === medicine.id ? <CheckCircle2 size={18} className="shrink-0 text-teal-700" aria-hidden="true" /> : <ArrowRight size={17} className="shrink-0 text-slate-400" aria-hidden="true" />}
            </button>
          </li>)}</ul>
        </div>}
        {search.status === 'success' && search.hasMore && <div className="border-t border-slate-100 p-3"><button type="button" onClick={loadMore} disabled={search.moreStatus === 'loading'} className="button-secondary w-full disabled:opacity-60">{search.moreStatus === 'loading' ? 'Loading more medicines...' : 'Load more medicines'}</button></div>}
        {search.moreStatus === 'error' && <div className="px-4 pb-4"><ErrorMessage title="Could not load more medicines" error={search.moreError} message={search.moreError?.message || 'Please try again.'} onRetry={loadMore} /></div>}
      </section>
      <section ref={comparisonRef} tabIndex={-1} aria-labelledby="comparison-title" className="min-w-0 scroll-mt-2 rounded-2xl border border-slate-200 bg-white p-4 focus-visible:outline-offset-[-3px] lg:sticky lg:top-24">
        <div className="flex items-center justify-between gap-2"><h2 id="comparison-title" className="text-sm font-semibold text-slate-900">2. Potential alternatives</h2>{original && <button type="button" aria-label="Back to medicines" onClick={returnToResults} className="flex min-h-11 shrink-0 items-center gap-1 text-xs font-medium text-teal-800 lg:hidden"><ArrowLeft size={14} aria-hidden="true" />Medicines</button>}</div>
        {original && <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1"><h3 className="min-w-0 break-words text-base font-semibold text-slate-900">{original.brand_name}</h3><p className="text-[11px] font-semibold tracking-wide text-slate-500 uppercase">Selected medicine</p></div><p className="mt-0.5 break-words text-xs leading-5 text-slate-600">{valueLabel(original.active_ingredient)} &middot; {valueLabel(original.strength)} &middot; {valueLabel(original.dosage_form)}</p>
          <Disclosure label="Medicine details & source"><CatalogDetails medicine={original} /><Source medicine={original} /></Disclosure>
        </div>}
        {comparison.status === 'idle' && <div className="py-8 text-center"><Pill size={28} className="mx-auto mb-3 text-teal-300" aria-hidden="true" /><p className="text-sm font-medium text-slate-700">Your alternatives will appear here</p><p className="mx-auto mt-2 max-w-xs text-xs leading-5 text-slate-500">Select a medicine from the results. Ingredients, individual strengths, form, route and release must all match.</p></div>}
        {comparison.status === 'loading' && <CompactLoading>Comparing documented attributes...</CompactLoading>}
        {comparison.status === 'error' && <ErrorMessage title="Could not load alternatives" error={comparison.error} message={comparison.error?.message || 'Please try again.'} onRetry={() => selectMedicine(original)} />}
        {comparison.status === 'empty' && <div className="mt-3 rounded-xl border border-slate-200 px-3 py-4" role="status"><h3 className="text-sm font-semibold text-slate-900">No matching candidates in this catalog</h3><p className="mt-2 text-xs leading-5 text-slate-600">No complete match, or incomplete or unsupported information. Undocumented route/release prevents matching. Ask your pharmacist or prescriber about your options.</p></div>}
        {comparison.status === 'success' && <div className="mt-3 space-y-3"><p role="status" className="text-xs font-medium text-slate-600">{comparison.records.length} potential {comparison.records.length === 1 ? 'alternative' : 'alternatives'} for professional review</p>{comparison.records.map((medicine) => <Candidate key={medicine.id} medicine={medicine} original={original} />)}</div>}
      </section>
    </div>
  </div>;
}
