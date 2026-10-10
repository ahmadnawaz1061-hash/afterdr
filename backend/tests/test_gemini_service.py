import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from google.genai import errors
from PIL import Image

from app.services import gemini_service
from app.services.gemini_service import extract_package, extract_prescription
from app.services.image_validation import (
    MAX_IMAGE_SIZE,
    ImageDimensionsError,
    ImageTooLargeError,
    ImageValidationError,
    validate_image,
)


@pytest.fixture(autouse=True)
def mock_ai(monkeypatch):
    monkeypatch.setenv("USE_MOCK_AI", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def image_bytes(format_name: str, size: tuple[int, int] = (20, 20)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color="white").save(buffer, format=format_name)
    return buffer.getvalue()


def test_mock_prescription_is_labeled_and_flags_an_ambiguous_field():
    result = extract_prescription(image_bytes("PNG"), "image/png")

    assert result.patient_name == "Synthetic Demo Patient"
    assert len(result.medicines) == 2
    ambiguous = result.medicines[1]
    assert ambiguous.name.startswith("Synthetic Demo")
    assert ambiguous.strength is None
    assert ambiguous.needs_review is True


def test_mock_package_is_labeled_and_flags_an_ambiguous_field():
    result = extract_package(image_bytes("JPEG"), "image/jpeg")

    assert result.brand_name.startswith("Synthetic Demo")
    assert result.registration_number is None
    assert result.needs_review is True


@pytest.mark.parametrize(
    ("format_name", "expected_mime"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg")],
)
def test_validation_uses_actual_image_content(format_name, expected_mime):
    assert validate_image(image_bytes(format_name)) == expected_mime


def test_oversized_file_is_rejected_before_decoding():
    with pytest.raises(ImageTooLargeError, match="5 MB"):
        validate_image(b"x" * (MAX_IMAGE_SIZE + 1))


def test_valid_but_unsupported_image_is_rejected():
    with pytest.raises(ImageValidationError, match="Only PNG and JPEG"):
        validate_image(image_bytes("GIF"))


def test_corrupt_image_is_rejected():
    with pytest.raises(ImageValidationError, match="Invalid or corrupt"):
        validate_image(b"\x89PNG\r\n\x1a\ncorrupt")


def test_excessive_dimensions_are_rejected():
    with pytest.raises(ImageDimensionsError, match="6000x6000"):
        validate_image(image_bytes("PNG", size=(6001, 1)))


def test_missing_key_only_errors_when_real_call_is_requested(monkeypatch):
    monkeypatch.setenv("USE_MOCK_AI", "false")

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is required"):
        extract_prescription(image_bytes("PNG"), "image/png")


def test_real_call_uses_structured_json_and_text_fallback(monkeypatch):
    captured = {}

    class Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                parsed=None,
                text=json.dumps({
                    "patient_name": None,
                    "doctor_name": None,
                    "medicines": [{
                        "name": "Visible Medicine Name",
                        "strength": None,
                        "dose": None,
                        "frequency": None,
                        "duration_days": None,
                        "instructions": None,
                        "needs_review": True,
                    }],
                }),
            )

    class Client:
        def __init__(self, api_key, http_options):
            captured["api_key"] = api_key
            captured["http_options"] = http_options
            self.models = Models()

    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-image-model")
    monkeypatch.setattr(gemini_service.genai, "Client", Client)

    result = extract_prescription(b"image-content", "image/png")

    assert result.medicines[0].needs_review is True
    assert result.medicines[0].strength is None
    assert captured["api_key"] == "test-key"
    assert captured["http_options"].timeout == gemini_service.GEMINI_TIMEOUT_MS
    assert captured["model"] == "test-image-model"
    assert captured["config"].system_instruction == gemini_service.SYSTEM_PROMPT
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].response_schema is gemini_service.PrescriptionExtraction
    assert captured["contents"][1].inline_data.mime_type == "image/png"
    assert captured["contents"][1].inline_data.data == b"image-content"


def test_real_call_uses_configured_request_timeout(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, api_key, http_options):
            captured["api_key"] = api_key
            captured["timeout"] = http_options.timeout

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setattr(gemini_service.genai, "Client", Client)

    gemini_service._client_and_model()

    assert captured == {"api_key": "test-key", "timeout": 12_500}


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number", "121"])
def test_invalid_request_timeout_is_rejected(monkeypatch, value):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", value)

    with pytest.raises(gemini_service.GeminiConfigurationError):
        gemini_service._client_and_model()


def test_provider_access_error_is_classified_and_logged_without_key(monkeypatch, caplog):
    class Models:
        def generate_content(self, **_kwargs):
            raise errors.ClientError(403, {"error": {"message": "Project denied"}})

    class Client:
        def __init__(self, **_kwargs):
            self.models = Models()

    secret = "super-secret-test-key"
    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    monkeypatch.setenv("GEMINI_MODEL", "test-image-model")
    monkeypatch.setattr(gemini_service.genai, "Client", Client)

    with caplog.at_level("WARNING"), pytest.raises(
        gemini_service.GeminiAccessError,
        match="Google project access",
    ):
        extract_prescription(b"image-content", "image/png")

    assert "category=GeminiAccessError" in caplog.text
    assert "status=403" in caplog.text
    assert secret not in caplog.text


@pytest.mark.parametrize(
    ("status_code", "message", "expected_error"),
    [
        (401, "Invalid API key", gemini_service.GeminiAccessError),
        (429, "Quota exhausted", gemini_service.GeminiQuotaError),
        (404, "Model not found", gemini_service.GeminiModelError),
        (408, "Request timed out", gemini_service.GeminiTimeoutError),
        (500, "Provider unavailable", gemini_service.GeminiServiceError),
    ],
)
def test_provider_failures_have_distinct_categories(
    status_code,
    message,
    expected_error,
):
    provider_error = errors.ClientError(
        status_code,
        {"error": {"message": message}},
    )

    with pytest.raises(expected_error):
        gemini_service._raise_provider_error(provider_error, "test-image-model")


def test_invalid_provider_json_has_a_safe_specific_error(monkeypatch):
    class Models:
        def generate_content(self, **_kwargs):
            return SimpleNamespace(parsed=None, text="not-json")

    class Client:
        def __init__(self, **_kwargs):
            self.models = Models()

    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-image-model")
    monkeypatch.setattr(gemini_service.genai, "Client", Client)

    with pytest.raises(
        gemini_service.GeminiResponseError,
        match="invalid extraction",
    ):
        extract_prescription(b"image-content", "image/png")
