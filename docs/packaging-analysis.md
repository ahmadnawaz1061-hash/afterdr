# Medicine Packaging Check

The Safety Checker now reads packaging photos and explains potential warning signs. A photo cannot prove physical authenticity. The verdict is computed in Python from separately attributed observations and reference comparisons; Gemini never sets the verdict.

## Configuration and demonstration

The backend uses the existing API key with configurable `GEMINI_MODEL=gemini-3.8-flash`. Real image analysis was tested successfully through the authenticated endpoint using a synthetic readable Brufen label and an isolated database. The former `gemini-3.5-flash` alias rejected Pydantic `additional_properties` in the GenerateContent schema and reached its daily free-tier quota. The current Flash model was checked against the same account and exercised with image input. There is no automatic model/provider fallback and no added API key. API key contents were preserved.

The request now uses an explicit provider-compatible Schema subset with nullable fields and one-based image indices. Full strict Pydantic validation remains authoritative after receiving the output; unsupported extra fields and model-selected verdicts remain forbidden. Daily-quota errors preserve the provider?s reset delay instead of suggesting a one-minute retry. Provider availability and account quotas can still change.

For a complete demonstration including database history and downloadable reports, use backend `USE_MOCK_AI=true` and frontend `VITE_USE_MOCKS=false`. Set backend `PACKAGING_DEMO_SCENARIO` to `consistent`, `suspicious_lookalike`, `registration_mismatch_demo`, or `unclear_image`, then restart the backend. Scenarios are deterministic and every simulated result carries a visible badge. A synthetic registration warning never changes the extracted number or the reference catalog. Saved simulations remain simulated after configuration changes and text corrections.

Frontend-only `VITE_USE_MOCKS=true` supports the upload/result demonstration, using `VITE_PACKAGING_DEMO_SCENARIO`. History is session-local. PDF/report persistence requires the backend demonstration above; frontend synthetic IDs cannot be submitted as real database records. There is no ordinary UI scenario selector.

No new runtime or system dependencies are required. Existing Pillow handles decoding, EXIF orientation, resizing, brightness, contrast, edge sharpness, and glare guidance. Cropping, text legibility, and cross-photo consistency use Gemini observations. Tesseract and OpenCV are not required.

## API and persistence

All new endpoints retain existing authentication and patient ownership checks:

| Endpoint | Behavior |
| --- | --- |
| `POST /api/verifications/analyze` | Multipart `images`: one to three photos, front first; optional `brand_name`, `manufacturer`, `registration_number` text corrections. Legacy single `file` alias and optional `trusted_reference` remain accepted for compatibility, but the reference upload is removed from the UI. Do not mix `file` and `images`. Returns saved structured assessment. |
| `POST /api/verifications/{id}/reanalyze` | JSON corrections to the seven extracted fields. Omitted fields preserve previous values; explicit null clears a value. Reuses stored observations, makes no Gemini call, and saves an immutable revision with `reanalysis_of`. |
| `GET /api/verifications/{id}` | Retrieves only the current patient's assessment. |
| `GET /api/verifications` | Recent checks, newest first, with `limit` (default 10, maximum 50) and `offset`. |

The seven nullable extracted fields are brand, active ingredient, strength, dosage form, manufacturer, registration number, and pack type. New verdicts are `likely_consistent`, `suspicious`, and `unable_to_assess`. Every result includes evidence origins, limitations, source, simulation marker, registration state, next steps, and `counterfeit_confirmed: false`. Risk scores describe warning evidence, not a probability of authenticity.

Existing `/extract`, legacy verification creation, and report endpoint contracts remain available. Existing `Verification` table constraints remain intact: new statuses map to legacy column values, while versioned JSON stores the full assessment and original observations. No migration is required. Legacy history is shown as requiring a new assessment rather than promoting old claims into new verdicts.

Raw uploaded photos are decoded and processed in memory, never persisted. PNG/JPEG content is authoritative regardless of filename. Limits are 5 MiB per photo, three analysis photos plus one optional reference, 6000 pixels per original side, and 12 MiB for the entire multipart request. Analysis copies are bounded to 2200 pixels and strip metadata. Frontend reserves space for multipart headers. Middleware enforces the total before multipart parsing, including streamed bodies. Unusable real front photos return an inconclusive assessment without consuming Gemini quota.

## Reference data and decision rules

`backend/data/known_brands.csv` contains 150 products derived from the existing documented DRAP snapshot. Source URLs and snapshot dates are retained. This is a limited historical dataset, not a verified current registry, live stock feed, recall service, or physical-packaging reference. Live online product lookup is also integrated separately; see below. Catalog absence is neutral. Synthetic sources are excluded by the loader. Optional fields can be missing.

Exact names and curated aliases are compared first. Similar names use normalized `difflib` similarity, with manufacturer/strength/form corroboration. A fuzzy name alone produces an inconclusive result. Ambiguous formulations cannot establish a registration mismatch. Registration states are `matched_reference`, `mismatch`, `not_visible`, `not_in_reference`, and `simulated_mismatch`; only an unambiguous sourced number can support an actual mismatch signal. A model's registration-validity assertions are ignored.

`RISK_WEIGHTS` in `packaging_assessment.py` defines contributions. High identity/registration findings contribute 35–40; medium findings 18–20; low findings 5. Printing contributes at most 12 and design at most 15. Each category contributes only its largest finding, avoiding duplication between vision and catalog evidence. Quality adds no counterfeit risk. Serious identity evidence or a score of at least 35 can produce `suspicious`. Unreadable image sets and poor photos with uncertain/conflicting identity remain inconclusive with a null score. A usable side photo can rescue an unusable front. Readable brand plus manufacturer and ingredient/strength, or brand plus ingredient and strength, can support a lower-risk result when a sourced catalog or unambiguous live DRAP match corroborates the details and no warning contribution exists. Two positive visual categories are no longer mandatory. Missing registration and manufacturer on a front photo do not alone block a supported product match. Internet matches identify a documented product; they do not authenticate the physical package.

Corrections are explicitly attributed to the user and retained separately from the original image reading. They are inputs to comparison, not independent proof. Packaging changes, salt synonyms, company ownership changes, and OCR errors can require human review.

## Cost, errors, and reports

One structured Gemini vision request includes all uploaded packaging photos. The former trusted-reference upload has been removed from the ordinary UI. Automatic SDK retries are disabled for this workflow. Provider quota, timeout, key/model configuration, and malformed-output failures return safe errors without internal traces. `PACKAGING_REQUESTS_PER_MINUTE` defaults to five per patient (allowed range 1–30), with one in-flight analysis per patient. Rate limits are process-local; a multi-worker deployment needs a shared limiter. Exact repeated photo evidence is reused from up to the latest 100 patient records; fingerprints include model, scenario, reference file hash, and analysis version. Text corrections do not call Gemini. Cancellation closes the client request but a provider call already sent may finish server-side.

The reporting page accepts `verification_id`, shows assessment evidence, collects optional purchase information, and saves a local report draft. Downloaded PDFs include status, risk, extracted fields, signals and origins, reference comparisons, next steps, limitations, and simulation marker. They are marked **DRAFT — NOT SUBMITTED**. No report is automatically sent to DRAP or another party. The new flow does not extract or evaluate batch numbers, expiry/manufacturing dates, barcodes, or QR codes; legacy report support remains unchanged.

## Verification

Run backend `.venv/Scripts/python.exe -m pytest -q`, frontend `npm.cmd test -- --run`, and `npm.cmd run build`. No frontend lint command exists. Backend tests cover all four demo scenarios, strict provider output, failure categories, real-mode simulation isolation, uploads, identity matching, ownership, cache/reanalysis, and PDF integration. Frontend tests cover uploads, cancellation, verdicts, corrections, history, and drafts. An isolated headless Edge check exercised 375px mobile and 1440px desktop layouts using intercepted demo API responses; it consumed no Gemini quota.

The supplied workspace has no `.git` metadata, so branch confirmation and Git diff commands cannot run here. A local source hash baseline was used to check scope. Scheduler, Prescription Reader, Medicine Alternatives, and database models were preserved.

Initial rework validation: the initial backend baseline was 255 passing tests. The final full run was 301 passed and one failed; all 47 new packaging tests passed. The failure is `test_automatic_scheduler_journey_updates_dashboard`, which freezes the scheduler clock but leaves the dashboard using real evening time. It also fails when run against the untouched source snapshot, so it was preserved rather than weakened or changing the out-of-scope scheduler. Frontend validation passed 126 tests across 13 files and the production build. Both checked viewport widths had no horizontal overflow, a visible Analyze button, and no browser runtime exceptions. No new runtime dependencies were installed.

## Implementation files

- Backend integration: `app/main.py`, `app/routers/verification.py`, `app/services/gemini_service.py`, `image_validation.py`, and `report_service.py`.
- New backend services: `packaging_contracts.py`, `packaging_assessment.py`, `packaging_reference.py`, `packaging_service.py`, and `packaging_upload_limit.py`, and `packaging_online_service.py` under `backend/app/services/`.
- Reference catalog: `backend/data/known_brands.csv`.
- Frontend pages: `VerificationPage.jsx` and `ReportingPage.jsx`.
- New upload/results components: `PackagingUploadCard.jsx`, `PackagingResults.jsx`, and `packagingUploads.js` under `frontend/src/components/verification/`.
- Frontend integration: `src/services/api.js`, `src/mocks/packagingDemo.js`, `src/components/common/StatusBadge.jsx`, and `src/components/layout/navigation.js`.
- Tests: new `backend/tests/test_packaging_online.py`, `backend/tests/test_packaging_analysis.py` and `frontend/src/pages/ReportingPage.test.jsx`; updated `backend/tests/test_routes.py` and `frontend/src/pages/VerificationPage.test.jsx`.
- Configuration/instructions: backend and frontend `.env.example`, `.github/instructions/backend.instructions.md`, and this document. The configured backend model was updated to the tested current Flash model; the API key was not changed.


## Live internet lookup update

The user-supplied comparison-photo section is replaced by automatic live searches of [DRAP?s public Pharmaceutical Product Price Index](https://e.dra.gov.pk/public/price). The source?s existing search form is read and submitted as a read-only product query. Search uses the readable brand, then deterministically compares manufacturer, ingredient, strength and form when available. Only unambiguous product details count as a match. Unknown names, multiple formulations, changed source pages and missing fields remain inconclusive. Web product details never overwrite image-extracted/user-corrected fields or become physical-authenticity/registration-validity claims.

The API adds `online_lookup` with status (`matched`, `not_found`, `unavailable`, `not_searched`, `simulated`), query, summary, nullable sourced product, source links, source name, and UTC search time. The results panel and PDF show online references separately. Correcting product identifiers performs another online lookup while reusing saved image observations. Duplicate checks refresh unavailable or expired lookups without another Gemini image request.

This uses existing httpx plus the standard-library HTML parser; no extra dependency, API key, or AI request is needed. Network destinations are fixed HTTPS DRAP endpoints with redirects disabled, 10-second request timeouts, a 2 MiB response cap, 15-minute success caching, a 60-second failure cache, and a bounded 128-entry cache. A source outage does not discard the packaging assessment. Simulation never queries the internet. Public index coverage and HTML structure are external limitations.

Google Search grounding was tested but returned a quota error on the account, so it is not part of the implemented runtime flow. Public generic-search responses were unreliable and were not used as product evidence. The successful real endpoint check returned HTTP 201, real extracted Brufen/Abbott details, `online_lookup.status=matched`, and a DRAP source link. This fixture is explicitly synthetic and establishes connectivity/integration only; it is not a claim about a real physical medicine pack.

Final update validation: 318 backend tests passed with the same existing scheduler clock failure, 128 frontend tests passed, and the production build succeeded. The real endpoint returned HTTP 201 with a matched live DRAP product reference. Mobile/desktop browser checks showed no horizontal overflow or runtime exceptions.

The final real lookup was also checked against formulation: the sourced match was `BRUFEN TABLETS 200MG`, tablet, 200 mg. Regression tests ensure plural ?Tablets? normalizes to ?tablet? and that unsupported/missing source strength cannot pass as a different suspension formulation.

Continued integration check: a two-photo synthetic Brufen request used real Gemini and live DRAP lookup, returned HTTP 201 and a matched product. An exact repeat reused the saved verification, a text correction created an immutable revision without another image request, and the report endpoint generated/downloaded a draft PDF containing the online product/source. All checks used an isolated in-memory database; patient records were untouched.

## After Dr branding and readability update

Visible branding, API title, browser titles, package metadata and report PDFs use After Dr. Existing database filenames and session-cookie identifiers remain compatible with saved records and signed-in users. Image-analysis cache version was advanced so new uploads do not reuse the older restrictive extraction. Product-form plurals and explicit Abbott/GSK printed manufacturer abbreviations are normalized. The scheduler journey test now freezes both scheduling and dashboard clocks, removing its time-of-day dependency.

Validation after the After Dr update: 327 backend tests and 128 frontend tests passed; the production build succeeded. One dependency deprecation warning remains, with no test failures. Real two-photo extraction, live DRAP match, cached repeats, immutable corrections and branded PDF download succeeded against an isolated test database. The synthetic label was correctly flagged as nonstandard packaging; an online product match does not suppress that visual finding. The running API reports After Dr API.
