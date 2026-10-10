"""Structured Gemini image transcription for prescriptions and packages."""

from __future__ import annotations

import os
import logging
import json
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field, ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

GEMINI_TIMEOUT_MS = 45_000
MAX_GEMINI_TIMEOUT_SECONDS = 120
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You transcribe medicine-related documents from images into structured data.
Transcribe only text that is visibly present in the supplied image. Never infer,
complete, or guess an illegible or obscured field: return null for that field and
set needs_review to true for the affected medicine or package. Do not provide
medical advice, recommendations, substitutions, or dosing guidance. Do not judge
or claim whether medicine or packaging is authentic. Return only the requested
structured extraction.
""".strip()


class ExtractionModel(BaseModel):
    """Base for schemas supported by Gemini structured output."""


class MedicineExtraction(ExtractionModel):
    name: str | None = None
    strength: str | None = None
    dose: str | None = None
    frequency: str | None = None
    duration_days: int | None = Field(default=None, ge=1)
    instructions: str | None = None
    needs_review: bool = True


class PrescriptionExtraction(ExtractionModel):
    patient_name: str | None = None
    doctor_name: str | None = None
    medicines: list[MedicineExtraction] = Field(default_factory=list)


class PackageExtraction(ExtractionModel):
    brand_name: str | None = None
    active_ingredient: str | None = None
    manufacturer: str | None = None
    registration_number: str | None = None
    batch_number: str | None = None
    mfg_date_text: str | None = None
    expiry_date_text: str | None = None
    strength: str | None = None
    dosage_form: str | None = None
    barcode_or_qr: str | None = None
    visual_packaging_flags: list[str] = Field(default_factory=list)
    image_quality_issues: list[str] = Field(default_factory=list)
    altered_label_flags: list[str] = Field(default_factory=list)
    needs_review: bool = True


class GeminiServiceError(RuntimeError):
    """Base error carrying a safe client-facing message and HTTP status."""

    status_code = 502
    public_message = "AI extraction is temporarily unavailable"


class GeminiConfigurationError(GeminiServiceError):
    status_code = 503
    public_message = "AI extraction is not configured on the backend"


class GeminiAccessError(GeminiServiceError):
    public_message = (
        "Gemini API access was denied. Check the backend API key and Google project access"
    )


class GeminiQuotaError(GeminiServiceError):
    status_code = 429
    public_message = "Gemini rate limit reached. Try again later"


class GeminiModelError(GeminiServiceError):
    status_code = 503
    public_message = "The configured Gemini model is unavailable. Check GEMINI_MODEL"


class GeminiTimeoutError(GeminiServiceError):
    status_code = 502
    public_message = "Gemini extraction timed out. Try again with a clear image"


class GeminiResponseError(GeminiServiceError):
    public_message = "Gemini returned an invalid extraction. Try a clearer image"


class GeminiEmptyResponseError(GeminiResponseError):
    public_message = "Gemini returned no extraction content. Try a clearer image"


def _environment_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def using_mock_ai() -> bool:
    """Return whether extraction should use labeled synthetic results."""
    return _environment_flag("USE_MOCK_AI")


def _configured_timeout_ms() -> int:
    raw_value = os.getenv("GEMINI_TIMEOUT_SECONDS", str(GEMINI_TIMEOUT_MS / 1000))
    try:
        seconds = float(raw_value)
    except ValueError as exc:
        raise GeminiConfigurationError(
            "GEMINI_TIMEOUT_SECONDS must be a number"
        ) from exc
    if not 0 < seconds <= MAX_GEMINI_TIMEOUT_SECONDS:
        raise GeminiConfigurationError(
            f"GEMINI_TIMEOUT_SECONDS must be between 0 and {MAX_GEMINI_TIMEOUT_SECONDS}"
        )
    return int(seconds * 1000)


def _mock_prescription() -> PrescriptionExtraction:
    return PrescriptionExtraction(
        patient_name="Synthetic Demo Patient",
        doctor_name="Synthetic Demo Prescriber",
        medicines=[
            MedicineExtraction(
                name="Synthetic Demo Medicine A",
                strength="500 mg",
                dose="1 tablet",
                frequency="Twice daily",
                duration_days=5,
                instructions="After food",
                needs_review=False,
            ),
            MedicineExtraction(
                name="Synthetic Demo Medicine B",
                strength=None,
                dose="1 capsule",
                frequency="Once daily",
                duration_days=3,
                instructions=None,
                needs_review=True,
            ),
        ],
    )


def _mock_package() -> PackageExtraction:
    return PackageExtraction(
        brand_name="Synthetic Demo Package Medicine",
        manufacturer="Synthetic Demo Manufacturer",
        registration_number=None,
        batch_number="SYNTH-DEMO-001",
        expiry_date_text="DEC 2030",
        strength="500 mg",
        dosage_form="tablet",
        needs_review=True,
    )


def _client_and_model() -> tuple[genai.Client, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiConfigurationError(
            "GEMINI_API_KEY is required when USE_MOCK_AI is false. "
            "Set it in the backend environment before requesting extraction."
        )

    model = os.getenv("GEMINI_MODEL", "").strip()
    if model.startswith("models/"):
        model = model.removeprefix("models/").strip()
    if not model:
        raise GeminiConfigurationError(
            "GEMINI_MODEL is required when USE_MOCK_AI is false. "
            "Set it to an available image-capable Gemini model."
        )
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=_configured_timeout_ms()),
    ), model


def _raise_provider_error(exc: errors.APIError, model: str) -> None:
    code = getattr(exc, "code", None)
    message = str(exc).lower()
    if code in {401, 403}:
        error_type: type[GeminiServiceError] = GeminiAccessError
    elif code == 429:
        error_type = GeminiQuotaError
    elif code == 404 or (code == 400 and "model" in message):
        error_type = GeminiModelError
    elif code in {408, 504}:
        error_type = GeminiTimeoutError
    else:
        error_type = GeminiServiceError

    logger.warning(
        "Gemini request failed: category=%s status=%s model=%s",
        error_type.__name__,
        code,
        model,
    )
    client_error = error_type(error_type.public_message)
    if isinstance(client_error, GeminiQuotaError):
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", {}) or {}
        client_error.retry_after = headers.get("retry-after")
    raise client_error from exc


def _schema_was_rejected(exc: Exception) -> bool:
    if isinstance(exc, errors.APIError) and getattr(exc, "code", None) != 400:
        return False
    message = str(exc).casefold()
    return any(
        marker in message
        for marker in ("response schema", "response_schema", "schema", "structured output")
    )


def _json_prompt(task_prompt: str, schema: type[ExtractionModel]) -> str:
    return (
        f"{task_prompt}\nReturn only one JSON object matching this JSON schema. "
        "Use null for every unclear value and do not add markdown fences:\n"
        f"{json.dumps(schema.model_json_schema(), separators=(',', ':'))}"
    )


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    if lines and lines[0].strip().casefold() in {"```", "```json"}:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _response_text(response: object, model: str) -> str:
    try:
        text = getattr(response, "text", None)
    except (ValueError, AttributeError):
        text = None
    if text:
        return _strip_json_fence(text)

    candidates = getattr(response, "candidates", None) or []
    prompt_feedback = getattr(response, "prompt_feedback", None)
    logger.warning(
        "Gemini returned no extraction content: candidate_count=%s "
        "prompt_feedback_present=%s model=%s",
        len(candidates),
        prompt_feedback is not None,
        model,
    )
    raise GeminiEmptyResponseError(GeminiEmptyResponseError.public_message)


def _generate(
    client: genai.Client,
    model: str,
    image_bytes: bytes,
    mime_type: str,
    schema: type[ExtractionModel],
    task_prompt: str,
    *,
    structured: bool,
) -> object:
    config_kwargs: dict[str, object] = {
        "system_instruction": SYSTEM_PROMPT,
        "response_mime_type": "application/json",
    }
    if structured:
        config_kwargs["response_schema"] = schema
    prompt = task_prompt if structured else _json_prompt(task_prompt, schema)
    return client.models.generate_content(
        model=model,
        contents=[
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
        config=types.GenerateContentConfig(**config_kwargs),
    )


def _extract(
    image_bytes: bytes,
    mime_type: str,
    schema: type[PrescriptionExtraction] | type[PackageExtraction],
    task_prompt: str,
) -> PrescriptionExtraction | PackageExtraction:
    client, model = _client_and_model()
    try:
        response = _generate(
            client,
            model,
            image_bytes,
            mime_type,
            schema,
            task_prompt,
            structured=True,
        )
    except (errors.APIError, ValueError) as exc:
        if not _schema_was_rejected(exc):
            if not isinstance(exc, errors.APIError):
                raise GeminiResponseError(
                    GeminiResponseError.public_message
                ) from exc
            _raise_provider_error(exc, model)
        logger.warning(
            "Gemini structured output was rejected; retrying JSON fallback: model=%s",
            model,
        )
        try:
            response = _generate(
                client,
                model,
                image_bytes,
                mime_type,
                schema,
                task_prompt,
                structured=False,
            )
        except errors.APIError as fallback_exc:
            _raise_provider_error(fallback_exc, model)
        except (httpx.TimeoutException, TimeoutError) as fallback_exc:
            logger.warning(
                "Gemini JSON fallback timed out: category=%s model=%s",
                GeminiTimeoutError.__name__,
                model,
            )
            raise GeminiTimeoutError(GeminiTimeoutError.public_message) from fallback_exc
        except ValueError as fallback_exc:
            raise GeminiResponseError(
                GeminiResponseError.public_message
            ) from fallback_exc
    except (httpx.TimeoutException, TimeoutError) as exc:
        logger.warning(
            "Gemini request failed: category=%s model=%s",
            GeminiTimeoutError.__name__,
            model,
        )
        raise GeminiTimeoutError(GeminiTimeoutError.public_message) from exc

    try:
        if getattr(response, "parsed", None) is not None:
            return schema.model_validate(response.parsed)
        return schema.model_validate_json(_response_text(response, model))
    except GeminiEmptyResponseError:
        raise
    except (ValidationError, ValueError) as exc:
        logger.warning(
            "Gemini response validation failed: schema=%s model=%s",
            schema.__name__,
            model,
        )
        raise GeminiResponseError(GeminiResponseError.public_message) from exc


def extract_prescription(image_bytes: bytes, mime_type: str) -> PrescriptionExtraction:
    """Transcribe visible prescription fields into an editable draft."""
    if using_mock_ai():
        return _mock_prescription()

    result = _extract(
        image_bytes=image_bytes,
        mime_type=mime_type,
        schema=PrescriptionExtraction,
        task_prompt=(
            "Transcribe the visible patient, prescriber, and medicine fields from "
            "this prescription. Mark each medicine that contains any unclear field "
            "for review."
        ),
    )
    return PrescriptionExtraction.model_validate(result)


def extract_package(image_bytes: bytes, mime_type: str) -> PackageExtraction:
    """Transcribe visible package fields without assessing authenticity."""
    if using_mock_ai():
        return _mock_package()

    result = _extract(
        image_bytes=image_bytes,
        mime_type=mime_type,
        schema=PackageExtraction,
        task_prompt=(
            "Transcribe only the visible brand, manufacturer, registration, batch, "
            "expiry, strength, and dosage-form fields from this medicine package."
        ),
    )
    return PackageExtraction.model_validate(result)
