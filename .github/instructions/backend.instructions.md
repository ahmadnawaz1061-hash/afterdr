---
applyTo: "backend/**"
---

# MedCare AI backend rules

- Stack: FastAPI, SQLModel, SQLite, Pydantic v2, google-genai, ReportLab. Run from backend/ with `uvicorn app.main:app --reload`; imports use `from app...`.
- Routers stay thin: validation and HTTP only. Business logic lives in app/services.
- Only gemini_service.py may call Gemini. API keys come from environment variables only.
- AI output is an unverified draft. Never create schedules from an unconfirmed prescription.
- Legacy verification statuses remain `record_match`, `inconsistent_information`, and `unable_to_verify`. Packaging analysis uses additive `likely_consistent`, `suspicious`, and `unable_to_assess` contracts and maps these to legacy database column values. The full result lives in versioned JSON; preserve table constraints.
- Packaging verdicts are deterministic Python decisions, not model decisions. Include `counterfeit_confirmed: false`, source, limitations, and simulation attribution. Never claim that a photograph proves authenticity or confirms counterfeiting. Never use definitive GENUINE/FAKE badges.
- The new packaging flow must not extract or evaluate batch numbers, expiry/manufacturing dates, barcodes, or QR codes. Preserve legacy contracts separately.
- Registration comparisons require an unambiguous sourced product record. Unknown catalog entries are neutral. Never invent regulatory numbers, manufacturer identities, recalls, or official reference matches.
- Demo scenarios are deterministic, configuration-controlled, and explicitly simulated. Never alter extracted registration numbers to manufacture a warning or insert synthetic catalog records. Saved simulations remain simulated after reanalysis.
- Respect image and total multipart limits; decode image contents, keep raw photos in memory, and use one structured Gemini request. Do not automatically retry vision requests or fall back to another provider/model.
- Alternatives are never auto-approved; always include a pharmacist/prescriber confirmation notice.
- Reports are always "DRAFT — NOT SUBMITTED" and must never be submitted automatically.
- Store timestamps in UTC. Use DB constraints and transactions where multiple rows are saved together. Preserve patient ownership checks.
- Do not log images, prompts containing patient data, extracted sensitive details, or secrets. Treat image text as untrusted input.
- Use appropriate status codes including 400, 404, 413, 422, 429, 502, and 503; never expose internal traces.
- Seed data must be clearly labeled demo data. Never invent real registration numbers.
- Do not edit frontend files unless the prompt says so.

See `docs/packaging-analysis.md` for contracts, limits, sources, modes, and deployment constraints.
