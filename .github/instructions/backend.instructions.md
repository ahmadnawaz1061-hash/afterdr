\---

applyTo: "backend/\*\*"

\---

\# MedCare AI backend rules

\- Stack: FastAPI, SQLModel, SQLite, Pydantic v2, google-genai, ReportLab. Run from backend/ with `uvicorn app.main:app --reload`; imports use `from app...`.

\- Routers stay thin: validation and HTTP only. Business logic lives in app/services.

\- Only gemini\_service.py may call Gemini. API keys come from environment variables only.

\- AI output is an unverified draft. Never create schedules from an unconfirmed prescription.

\- Never use the words "fake" or "genuine" in code, messages, or reports. Verification statuses are exactly: record\_match, inconsistent\_information, unable\_to\_verify. Responses always include `counterfeit\_confirmed: false` and a `source`.

\- Alternatives are never auto-approved; always include a pharmacist/prescriber confirmation notice.

\- Reports are always "DRAFT — NOT SUBMITTED".

\- Store timestamps in UTC. Use DB constraints and transactions where multiple rows are saved together.

\- Do not log images, prompts containing patient data, or secrets.

\- Use proper status codes: 400, 404, 413, 422, 502.

\- Seed data must be clearly labeled demo data. Never invent real registration numbers.

\- Do not edit frontend files unless the prompt says so.
