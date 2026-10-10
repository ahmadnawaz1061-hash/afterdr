# After Dr frontend

Local React + Vite + Tailwind CSS scaffold based on sections 3–4 of
`../After_Dr_Complete_Architecture.md` (the supplied workspace architecture file).

## Run

Use Node.js 22.12+ (or 20.19+).

```sh
cd frontend
npm install
npm run dev
```

`npm run build` creates `dist/`; `npm run preview` serves the production build.
For this workspace, a portable Node runtime is also available under the ignored
`.tools/` directory. From `frontend/`, you can start the installed app in PowerShell
without changing your system PATH:

```powershell
../.tools/node-v22.23.3-win-x64/node.exe node_modules/vite/bin/vite.js
```

Tailwind uses its official `@tailwindcss/vite` integration:
https://tailwindcss.com/docs/installation/using-vite

## Scope

- Routes: `/`, `/dashboard`, `/prescription`, `/scheduler`, `/alternatives`,
  `/verification`, `/reporting`, plus a not-found page.
- Shared navbar, collapsible desktop sidebar, and mobile hamburger disclosure.
  Escape closes the mobile navigation and returns focus to its toggle.
- Landing includes a hero, five feature summaries, and a **Try the demo** link
  to the dashboard. Its on-demand catalog preview uses `searchMedicine('')`,
  with loading, empty, success, and retryable error states. Mock records show
  their demo badges. The core landing content stays usable if the request fails.
- The remaining pages retain a **Preview state** selector for loading, empty,
  success, and error until their individual implementations.
- Sample content lives in `src/mocks/demoData.js` and displays the demo badge.
- Alternative warnings and report draft status stay visible in every state.
- Reusable image selection and medicine display components are ready to connect.
  API uploads, scheduling, searches, and report downloads remain future work.

All HTTP calls belong in `src/services/api.js`; components import service
functions, never axios. Copy `.env.example` to `.env` to enable mock API responses,
and adjust the backend URL if needed. The only frontend settings are
`VITE_API_BASE_URL` and `VITE_USE_MOCKS`; never place credentials in frontend code.
The scaffold works without a backend and does not fall back to demo responses
when a real API call fails.

For deployment, configure the host to serve `index.html` for client routes so
direct visits and refreshes work with BrowserRouter.

## Manual checks

On Landing, follow the demo and five feature links, then load the catalog preview.
Check it with mock mode enabled and with unavailable or empty API responses.
On remaining routes, switch through all four preview states. Verify retry,
sample buttons, active navigation, keyboard focus, the skip link, desktop
collapse, and mobile navigation at narrow widths. Ensure alternatives retain
their confirmation notice and reports retain `DRAFT — NOT SUBMITTED`.

## Shared components

- `FileUploader`: `onFileSelect(fileOrNull)`, optional `label`, and `disabled`.
  Supports drag/drop and the native keyboard-accessible file picker. Accepts one
  nonempty PNG/JPEG up to 5 × 1024 × 1024 bytes. Invalid replacements retain the
  previous selection. Removal or a preview decoding failure sends `null`.
  Preview URLs are released on replacement/removal/unmount. Files stay local;
  server-side upload validation must also enforce file contents and size.
- `LoadingState`: optional `title` and `message`; announces loading politely.
- `ErrorMessage`: optional `title`, `message`, `onRetry`, and `retryLabel`;
  announces errors with `role="alert"`. Retry appears only with a callback.
- `StatusBadge`: `status` accepts `pending`, `taken`, `missed`, `record_match`,
  `inconsistent_information`, or `unable_to_verify`. Unknown values retain the
  existing `Unable to verify` fallback. `DemoBadge` and `DraftBadge` remain exports.
- `MedicineCard`: `medicine`, optional `isDemo` and `isAlternative`.
- `MedicineTable`: `medicines` (defaults to `[]`), optional `caption`, `isDemo`,
  and `isAlternative`. Uses semantic headers and a focusable horizontal scroll
  region for narrow screens. Both medicine components support empty data.

Medicine records use `id`, `name`, `strength`, `dose`, `frequency`,
`duration_days`, optional `instructions`, `needs_review`, and `status`.
Missing instructions are displayed as `Not provided`; no dose is inferred.
Mark demo records with `is_demo: true` (as in `demoMedicines` in
`src/mocks/demoData.js`), or pass `isDemo` for an entire demo dataset.
Mark candidate alternatives with `is_alternative: true`, or pass `isAlternative`;
both display the required pharmacist/prescriber confirmation notice.

Run `npm test` for component interaction and accessibility-markup checks.
These use jsdom and do not replace browser or screen-reader testing.

## Mock data and API

`VITE_USE_MOCKS=true` enables the exported `USE_MOCKS` flag. Missing values,
`false`, and any other value use real HTTP. Restart Vite after changing `.env`.
The three service functions from architecture section 4 Step 4 keep their real
request contracts, timeouts, and `response.data` return values. The configured
axios instance is also the default export; direct calls on that instance always
use HTTP, so components should call the named service functions.

In mock mode, every named service resolves after 600 ms with an independent
copy of its result. There is no extra response wrapper:

| Function | Result |
| --- | --- |
| `extractPrescription(file)` | Review-required prescription object with two medicines; the sample does not analyze the file or save a prescription. |
| `getTodaySchedule()` | Array of three sample dose records, with UTC timestamps for today's date in Asia/Karachi. |
| `searchMedicine(query)` | Catalog array filtered by brand or ingredient, ignoring case and surrounding spaces; blank searches return all three, unmatched searches return `[]`. |

`src/mocks/demoData.js` exports `demoPrescription`, `demoTodaySchedule`,
`createDemoTodaySchedule`, `demoCatalog`, `demoAlternatives`,
`demoPackageExtraction`, and `demoVerificationResult`, alongside the existing
page previews and medicine card example. Alternatives are mapped by catalog ID:
A and B are sample candidates for each other; C has no compatible candidate.
The package and verification samples describe the same manufacturer mismatch.
Package extraction and verification fixtures are ready for their later service
functions; Step 4's API module currently has only its three named functions.

The architecture gives explicit prescription, package, and verification shapes;
schedule records follow its dose model and catalog records its medicine model.
`is_demo: true` is provenance metadata on every mock result/record so consuming
views can display **Simulated demo data**. Existing medicine components recognize
this field. Catalog entries use `brand_name`, matching the API contract; map that
to a card's `name` when displaying catalog products. Alternative views must also
pass `isAlternative` or retain the candidate's `is_alternative` marker.

Schedule samples represent a separate, already-confirmed demo record; loading
an extraction does not create doses. All catalog names and ingredients are
demonstration labels; unknown package fields and registration numbers stay null.

## Accessibility and responsive review

Reviewed the existing seven routes and not-found page in Chrome on 10 October
2026 at 375px, with additional 320px and 1280px checks. The six placeholder
pages were checked in all four states; Landing's catalog was checked through
loading, empty, success, and error responses.

- Initial load preserves the natural tab order, with the skip link first.
  Route changes close mobile navigation, focus main content, and reset scroll.
- Sticky-header scroll clearance keeps headings and keyboard targets visible.
- Catalog actions keep the same button mounted through loading and retry;
  repeated activation is ignored while loading. Placeholder actions move focus
  to their result region when the triggering button is removed.
- Mobile selectors use the full available width and 16px text. Form and button
  borders have stronger contrast; shared page sections use consistent spacing.
- All 48 axe-core viewport/state scans passed the selected WCAG A/AA rules,
  with no horizontal page overflow. Keyboard flows and mobile screenshots were
  also reviewed. All 57 component/service tests and the production build passed.

These checks cover Chrome and automated accessibility rules; they do not certify
screen-reader behavior or other browser engines. `src/services/api.js` was
unchanged during this review, including all function signatures.
