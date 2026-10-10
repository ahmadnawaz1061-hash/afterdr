# Module C: Alternative Medicine Finder

Module C implements the architecture's catalog lookup and potential-alternative comparison. It uses real Pakistan records from DRAP public sources. The page is available at `/alternatives` after signing in through the existing account flow.

## Run

From the repository root, prepare the catalog once:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.import_alternative_catalog
```

The import inserts only missing medicine records. It creates no patients, prescriptions, schedules, checks or reports. Running it again skips identical records. A conflicting registration aborts the whole transaction and preserves existing records.

Start or restart the backend in this terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm.cmd run dev -- --port 5173 --strictPort
```

Open `http://localhost:5173/alternatives`. Sign in, search `Panadol`, select its 500 mg conventional tablet record, and inspect the potential Provas candidate. Search `Bactrim` to inspect an incomplete record: its undocumented route/release prevent matching. Search an absent product to exercise empty results. Stop the backend to exercise errors and retries.

Module C always requests real Pakistan catalog data, even when `VITE_USE_MOCKS=true` enables fictional previews elsewhere. No `.env` changes are required. The existing frontend API base URL, cookies, account protection and backend CORS still apply.

## Compact interface

Search and browsing share a short toolbar. Desktop shows compact medicine rows beside a sticky alternatives panel. The results list has its own bounded scroll area, so loading additional records does not push alternatives down the page. Every row shows the product name, ingredient, strength, form and registration to help select the exact product.

Selecting a product immediately focuses the comparison and brings it into view. Phones stack the panels and provide a **Medicines** return control. The alternative card shows its brand, strength, ingredient, form, route, release, manufacturer and match summary. Pharmacist/prescriber guidance and the clinical-interchangeability disclaimer stay visible. **Medicine details & source** and **Comparison details & source** expand the full attributes, five match reasons, comparison table and evidence links. The underlying catalog and matching rules are unchanged by the interface redesign.

## Ownership and merge boundaries

Changed existing files:

- `backend/app/routers/medicines.py`
- `backend/app/services/alternative_service.py`
- `backend/tests/test_alternative_service.py`
- `frontend/src/pages/AlternativesPage.jsx`

New Module C files:

- `backend/app/services/alternative_catalog.py`
- `backend/data/alternative_medicines_pk.json`
- `backend/scripts/import_alternative_catalog.py`
- `backend/scripts/collect_alternative_catalog.py`
- `backend/tests/test_alternative_catalog.py`
- `backend/tests/test_alternative_collection.py`
- `frontend/src/services/alternativesApi.js`
- `frontend/src/services/alternativesApi.test.js`
- `frontend/src/pages/AlternativesPage.test.jsx`
- `docs/module-c-alternative-finder.md`

Shared models, schemas, database helpers, repositories, app entrypoints, authentication, shared frontend services, mock fixtures, styles, package manifests, lockfiles and Modules A/B/D/E do not need edits for this module. The medicine router defines its additional response metadata locally; the frontend uses its own service file and the existing configured HTTP client.

Stage only this module from the repository root:

```powershell
git add -- backend/app/routers/medicines.py backend/app/services/alternative_service.py backend/tests/test_alternative_service.py frontend/src/pages/AlternativesPage.jsx backend/app/services/alternative_catalog.py backend/data/alternative_medicines_pk.json backend/scripts/import_alternative_catalog.py backend/scripts/collect_alternative_catalog.py backend/tests/test_alternative_catalog.py backend/tests/test_alternative_collection.py frontend/src/services/alternativesApi.js frontend/src/services/alternativesApi.test.js frontend/src/pages/AlternativesPage.test.jsx docs/module-c-alternative-finder.md
git diff --cached --stat
git diff --cached
git commit -m "Implement Module C Pakistan medicine alternative finder"
```

Coordinate ownership of `medicines.py`, `alternative_service.py` and `AlternativesPage.jsx` with the team. Other modules may read the medicine repository or catalog without editing Module C's matching logic. Existing changes made before this task, such as the authentication dependency fix, belong in separate commits. Environment files and the local SQLite database must remain untracked.

## API compatibility

| Request | Behavior |
| --- | --- |
| `GET /api/medicines/search?q=Panadol&catalog=drap_pk` | First 10 matching records from the documented Pakistan snapshot. |
| `GET /api/medicines/search?catalog=drap_pk&offset=10` | Next 10 records; supports browsing the whole catalog. |
| `GET /api/medicines/{id}/alternatives?catalog=drap_pk` | Potential candidates from the same documented Pakistan snapshot. |
| Either endpoint without `catalog` | Preserves the existing all-catalog behavior for other modules. |

The original response fields and substitution notice remain intact. Pakistan responses additionally include `source_url`, `source_checked_at`, and `formulation_source_url` where available. Existing responses do not gain null metadata fields. Requests require the existing authenticated user; unknown IDs return 404, invalid query values return 422, and an insufficiently documented original returns an empty candidate list.

The search compares literal brand/ingredient substrings, escaping wildcard characters. It never invents a medicine when search fails. A `drap_pk` marker alone does not establish provenance: records must match the documented snapshot fields. `offset` defaults to 0 (maximum 10,000), and `limit` defaults to 10 (maximum 50). The frontend appends results with **Load more medicines**, preserves the selected medicine, retries failed pages and cancels stale requests when the search changes. Each candidate also includes an explicit informational-use and no-unapproved-treatment-change disclaimer.

## Matching rules

`normalize_strength` remains compatible with the existing authenticity/verification callers on `main`. Module C uses the separate strict `normalize_matching_strength` helper for all alternative signatures; unsupported values are excluded there. This prevents the stricter parser from collapsing distinct unsupported strengths into equal `None` values in another module's comparisons.

- Exact active-ingredient identities after case/whitespace normalization. Salts and esters are preserved; synonyms and clinical equivalents are not inferred.
- Each ingredient is bound to its own strength before sorting combination pairs. Reordering both ingredients and corresponding strengths is supported; swapped amounts are excluded.
- Positive mass strengths are converted exactly among kg/g/mg/microgram units. Positive mass-per-volume concentrations are compared exactly with rational arithmetic. For example, `0.5 g` matches `500 mg`, and `500 mg/5 mL` matches `100 mg/mL`.
- Dosage form, route and release type must match exactly after case/whitespace normalization. Coated/uncoated and different release descriptions remain distinct when documented.
- Missing/unknown fields, duplicate ingredients, ingredient/strength count mismatches, unsupported units, percentages, IU, approximate values and mixtures with ambiguous shared denominators are excluded.
- The original product is excluded. Demo records cannot be matched against real records. Pakistan queries also exclude foreign or undocumented records.
- Every candidate carries the five match reasons, a source label and the pharmacist/prescriber confirmation notice. The module never changes a prescription or recommends doses.

This compares catalog attributes only. It does not evaluate bioequivalence, inactive-ingredient allergies, contraindications, treatment history, stock availability, product authenticity or current registration renewal. Pharmacist/prescriber assessment remains necessary.

## Real sources and coverage

The expanded snapshot contains **150 unique real DRAP-listed registrations**. This counts different strengths as separate registered products, and never counts packaging repeats as new medicines. The JSON snapshot is about **128 KiB** with LF line endings. Searches read the imported local SQLite medicine table; provenance comes from the JSON snapshot. The running web application makes no external DRAP/manufacturer API calls. Collection is an explicit offline maintenance step, separate from patient requests.

Registration, company and composition come from 37 distinct DRAP price-index pages. Most newly collected records are single-ingredient tablets/capsules, with original source product names and composition text retained for review. The original eight manually curated records remain unchanged. Source URLs, evidence notes, per-record check dates and collection audit metadata are stored in `backend/data/alternative_medicines_pk.json`; these sources were checked on 10 October 2026.

- [DRAP price index, page 515](https://e.dra.gov.pk/public/price?page=515): Provas record.
- [DRAP price index, page 516](https://e.dra.gov.pk/public/price?page=516): Panadol, Calpol, Fevadol, Bactrim and Supracombin records.
- [DRAP price index, page 700](https://e.dra.gov.pk/public/price?page=700): Neodipar SR strengths.
- [DRAP price index, page 599](https://e.dra.gov.pk/public/price?page=599): Getzid MR 60 mg registration 102855 and other listed records.
- [Getz Pharma Pakistan Getzid MR leaflet](https://getzpharma.com/wp-content/uploads/2023/03/Getzid-MR-Range-Leaflet-PAK.pdf): page 1 explicitly documents oral administration, modified release and 30/60 mg compositions. This supplements the exact DRAP-listed 60 mg registration; it is not registration evidence by itself.
- [329th Registration Board minutes](https://www.dra.gov.pk/wp-content/uploads/2023/10/Minutes-of-329-Meting-of-RB.pdf#page=69): printed pages 69 and 72–73 distinguish oral conventional immediate-release uncoated paracetamol tablets from the advance formulations and identify conventional Panadol/Provas. These historical formulation descriptions supplement the current price listings.
- [DRAP product-database explanation](https://www.dra.gov.pk/news_updates/regulatory_updates/updated-database-of-pharmaceutical-and-biological-drug-product/): describes the reference purpose and limitations of the public database.

**Three of the 150 records have documented route and release:** Panadol, Provas and Getzid MR 60 mg. Only Panadol/Provas currently form a complete matching pair. The other **147** records retain `unknown` for undocumented route/release attributes and cannot generate alternatives. More catalog records therefore improve search coverage without implying 150 substitution-ready products. A brand suffix such as SR does not supply a reviewed release profile by itself. Unknown fields are displayed as “Not documented.”

The main registration/SmPC portals were partly inaccessible during development. Price-index inclusion and historical minutes do not prove current renewal status, availability or clinical interchangeability. This is a reference snapshot, not a complete Pakistan medicine database or automatic regulatory verification. DRAP pagination may move as records are added; recheck the exact registration number rather than relying solely on a page number. An internally inconsistent Albendal row (registration 019652: product name says suspension, composition says tablet) was excluded and recorded in the collection audit.

## Expanding or enriching the snapshot

The Module C collector downloads a bounded set of public DRAP HTML pages; it does not use an undocumented external API or collect the whole portal. It accepts unambiguous single-ingredient per-tablet/capsule declarations, rejects unclear compositions and conflicting forms, preserves the original text, deduplicates registration numbers, and keeps new route/release fields unknown. Raw pages are cached in ignored `.tools/module-c-catalog-research/`. A short source set or download/parser failure leaves the existing snapshot untouched. When the target is already met, rerunning preserves the snapshot and its original audit.

For example, from `backend/`, expand to at least 200 unique records:

```powershell
.\.venv\Scripts\python.exe -m scripts.collect_alternative_catalog --target 200
.\.venv\Scripts\python.exe -m scripts.import_alternative_catalog
```

Use `--pages 618 619 620 621 622` to select source pages, or `--refresh` to refetch selected pages instead of using their local research cache. If too few acceptable unique registrations are available, select additional pages and rerun. The target is a minimum; existing records are never removed to meet a smaller target. Collection preserves manually reviewed records and does not automatically update an existing registration's formulation.

To expand **matching** coverage, separately add product-specific Pakistan formulation evidence to incomplete records. Registration must still have an official DRAP link. Formulation links permit DRAP or the specifically reviewed Getzid Pakistan manufacturer leaflet; additional manufacturer documents require review and corresponding Module C link validation. Preserve ingredient-strength ordering, salt/base distinctions and precise dosage forms. A pharmacist should review the formulation mapping before real substitution decisions. Restart the backend after changing the snapshot because provenance is cached. The importer rejects changed/conflicting existing registrations instead of silently overwriting them; review and reconcile those rows explicitly.

Synthetic records appear only in isolated tests of matching edge cases, never in this module's user-facing catalog.

## Validation

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_alternative_service.py tests/test_alternative_catalog.py tests/test_alternative_collection.py tests/test_routes.py -q
```

```powershell
cd frontend
npm.cmd test -- --configLoader runner
npm.cmd run build
```

Backend coverage includes swapped combination amounts, units/concentrations, exact arithmetic, missing/unknown attributes, salts/forms, original exclusion, provenance, import rollback/idempotence, authentication, all 150 records reachable across nonoverlapping pages, source extraction ambiguity/conflicts, unchanged snapshots on unsuccessful collection and API compatibility. Frontend coverage includes real endpoint contracts, malformed responses, loading/empty/error/retry states, source links, comparisons, later-page failures/retries, stale pages and unmount cancellation. Shared frontend regression tests run with the module tests.
