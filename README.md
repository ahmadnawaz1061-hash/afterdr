# MedCare AI

MedCare AI is a React/Vite frontend with a FastAPI backend. Users create an
account, sign in, and store prescriptions, schedules, verification results, and
report drafts under their own patient record.

## Run locally

Use Python 3.11 or newer and Node.js 20.19+ or 22.12+.

Start the backend from the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

On macOS or Linux, activate the virtual environment with
`source .venv/bin/activate` and copy the example with `cp .env.example .env`.
The API is available at `http://localhost:8000`, its health endpoint is
`http://localhost:8000/api/health`, and interactive documentation is at
`http://localhost:8000/docs`. FastAPI creates empty database tables on startup.
Create an account from the website; no patient or medicine records are inserted
automatically.

In a second terminal, start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`. Configure `frontend/.env` with:

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api
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
