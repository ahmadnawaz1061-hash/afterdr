# After Dr

After Dr is a React/Vite frontend with a FastAPI backend. Users create an
account, sign in, and store prescriptions, schedules, verification results, and
report drafts under their own patient record.

## Run locally

Use Python 3.11 or newer and Node.js 20.19+ or 22.12+.

### Windows quick start

From the `afterdr-main` directory, prepare dependencies and missing `.env` files:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Setup preserves existing `.env` files and generates a random authentication
secret for a new backend environment. Add your key to `GEMINI_API_KEY` in
`backend/.env`; keep API keys out of the frontend. Live image extraction needs
this key. To try simulated extraction instead, set `USE_MOCK_AI=true`.

Run these commands in two separate terminals from `afterdr-main`:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-backend.ps1
```

```powershell
powershell -ExecutionPolicy Bypass -File .\start-frontend.ps1
```

Open `http://localhost:5173`. The scripts use the project virtual environment
directly and keep the frontend on port 5173. During development, Vite forwards
same-origin `/api` requests to `http://127.0.0.1:8000`, so authentication also
works when `npm run dev` selects another available port.
Press Ctrl+C in each terminal to stop it. The backend startup script watches
`.env` and restarts automatically when you save configuration changes. If you
start Uvicorn manually, restart it after editing `.env` or add
`--reload-include .env` to its command.

### Manual setup

Start the backend from the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
uvicorn app.main:app --reload --reload-include .env
```

On macOS or Linux, activate the virtual environment with
`source .venv/bin/activate` and copy the example with `cp .env.example .env`.
The API is available at `http://localhost:8000`, its health endpoint is
`http://localhost:8000/api/health`, and interactive documentation is at
`http://localhost:8000/docs`. FastAPI creates database tables and imports the
bundled Pakistan medicine catalog on startup. Create an account from the website;
patient records are never seeded unless demo seeding is explicitly enabled.

In a second terminal, start the frontend:

```powershell
cd frontend
npm ci
if (!(Test-Path .env)) { Copy-Item .env.example .env }
npm run dev
```

The frontend runs at `http://localhost:5173`. Configure `frontend/.env` with:

```dotenv
VITE_API_BASE_URL=/api
VITE_USE_MOCKS=false
```

## Backend environment

Create `backend/.env` from `backend/.env.example`. Environment files are ignored
by Git and must not be committed.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Database connection URL. The local default is `sqlite:///./medcare.db`. |
| `ALLOWED_ORIGINS` | Comma-separated frontend origins allowed by CORS. Do not use `*`. |
| `AUTH_SECRET_KEY` | Random secret of at least 32 characters used to sign login sessions. |
| `AUTH_TOKEN_MINUTES` | Login lifetime in minutes. |
| `AUTH_COOKIE_SECURE` | Set to `true` when frontend and backend use HTTPS. |
| `SEED_DEMO_DATA` | Keep `false` for the live application. |
| `IMPORT_MEDICINE_CATALOG` | Defaults to `true`: import the bundled DRAP catalog on startup. Set `false` to manage imports manually. |
| `GEMINI_API_KEY` | Server-side Gemini key, required only for live extraction. |
| `GEMINI_MODEL` | Image-capable Gemini model name. |
| `GEMINI_TIMEOUT_SECONDS` | Provider request timeout, from 0 to 120 seconds. |
| `USE_MOCK_AI` | Set to `true` to return labeled simulated extraction results. |

For local extraction testing without network access or a Gemini key, set:

```dotenv
USE_MOCK_AI=true
```

Restart the backend after changing environment variables. The rest of the API,
including database persistence, scheduling, verification, and PDF generation,
continues to run locally in this mode.

## Pakistan medicine catalog and search

The alternative finder uses 150 sourced DRAP product registrations from
`backend/data/alternative_medicines_pk.json`, including familiar brands such as
Panadol, Augmentin, Amoxil, Brufen, Flagyl, Risek, Glucophage and Norvasc.
Different strengths/forms are separate products. This is a curated project
sample, not a verified ranking of Pakistan's most-used medicines or a complete
market inventory. Each record retains its source and check date; targeted
search records also retain the original product name, composition and search
term. DRAP search results require entering the registration number on the
linked public price-index page.

Startup imports are offline, transactional and repeatable. Matching records
are skipped, conflicting registrations are reported, and patient data and
existing medicine IDs are preserved. Older records may remain in an existing
database; the alternative finder only exposes the current 150-record snapshot.
To load the catalog into an already running installation, run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_alternative_catalog
```

Restart the backend after updating the bundled JSON, then refresh the frontend.
Brand/ingredient search ignores case, tolerates small spelling mistakes and
adjacent-letter swaps, and ranks direct matches first. Spelling suggestions
appear when no direct matches exist and are labeled in the UI. Numbers must
match exactly, including decimals. Browse and search both support pagination.
Try `Panadol`, `panadlo`, `brufn 400mg`, or `amoxicillin`.

Search aliases and spelling similarity never establish alternative eligibility.
The comparison still requires documented matching ingredients, individual
strengths, form, route and release. Missing clinical attributes stay `unknown`;
they are not estimated. Some searchable records therefore have no alternatives.
No live registration status, stock, pricing or treatment advice is inferred.

## Deploy the backend

The backend [Procfile](backend/Procfile) starts the service with:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

When creating a Render web service, use `backend` as the root directory, install
with `pip install -r requirements.txt`, and configure `DATABASE_URL`,
`ALLOWED_ORIGINS`, `AUTH_SECRET_KEY`, `AUTH_COOKIE_SECURE=true`, `GEMINI_MODEL`,
`GEMINI_API_KEY`, and `USE_MOCK_AI=false` in the hosting dashboard. Set
`ALLOWED_ORIGINS` to the deployed frontend origin.

SQLite files may be lost on hosts with ephemeral filesystems. Attach persistent
storage and point `DATABASE_URL` to that disk when records must survive restarts,
for example `sqlite:////var/data/medcare.db`.

Deploy the frontend to a static host, set `VITE_API_BASE_URL` to the deployed
backend URL ending in `/api`, and configure SPA fallback routing to `index.html`.
