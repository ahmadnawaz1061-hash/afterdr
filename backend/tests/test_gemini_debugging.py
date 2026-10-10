import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import errors
from PIL import Image

from app.main import app
from app.routers import prescriptions as prescriptions_router
from app.services import gemini_service


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def real_mode(monkeypatch) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-image-model")


def test_missing_key_fails_only_when_real_path_is_called(monkeypatch):
    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "test-image-model")

    with pytest.raises(gemini_service.GeminiConfigurationError):
        gemini_service.extract_prescription(b"image", "image/png")


def test_model_prefix_is_removed_and_missing_model_is_rejected(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, api_key, http_options):
            captured["api_key_set"] = bool(api_key)

    real_mode(monkeypatch)
    monkeypatch.setenv("GEMINI_MODEL", " models/example-image-model ")
    monkeypatch.setattr(gemini_service.genai, "Client", Client)

    _, model = gemini_service._client_and_model()
    assert model == "example-image-model"
    assert captured == {"api_key_set": True}

    monkeypatch.setenv("GEMINI_MODEL", "  ")
    with pytest.raises(gemini_service.GeminiConfigurationError):
        gemini_service._client_and_model()


def test_bad_model_name_is_classified(monkeypatch):
    class Models:
        def generate_content(self, **_kwargs):
            raise errors.ClientError(
                404,
                {"error": {"message": "Model not found"}},
            )

    class Client:
        def __init__(self, **_kwargs):
            self.models = Models()

    real_mode(monkeypatch)
    monkeypatch.setattr(gemini_service.genai, "Client", Client)

    with pytest.raises(gemini_service.GeminiModelError):
        gemini_service.extract_prescription(b"original-image", "image/png")


def test_empty_response_reports_a_specific_error(monkeypatch):
    class Models:
        def generate_content(self, **_kwargs):
            return SimpleNamespace(
                parsed=None,
                text=None,
                candidates=[],
                prompt_feedback=SimpleNamespace(block_reason="OTHER"),
            )

    class Client:
        def __init__(self, **_kwargs):
            self.models = Models()

    real_mode(monkeypatch)
    monkeypatch.setattr(gemini_service.genai, "Client", Client)

    with pytest.raises(gemini_service.GeminiEmptyResponseError):
        gemini_service.extract_prescription(b"original-image", "image/png")


def test_schema_rejection_retries_and_parses_fenced_json(monkeypatch):
    calls = []

    class Models:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise errors.ClientError(
                    400,
                    {"error": {"message": "Response schema is unsupported"}},
                )
            payload = {
                "patient_name": "Visible Patient",
                "doctor_name": None,
                "medicines": [],
            }
            return SimpleNamespace(
                parsed=None,
                text=f"```json\n{json.dumps(payload)}\n```",
            )

    class Client:
        def __init__(self, **_kwargs):
            self.models = Models()

    real_mode(monkeypatch)
    monkeypatch.setattr(gemini_service.genai, "Client", Client)

    result = gemini_service.extract_prescription(
        b"original-image",
        "image/png",
    )

    assert result.patient_name == "Visible Patient"
    assert len(calls) == 2
    assert calls[0]["config"].response_schema is gemini_service.PrescriptionExtraction
    assert calls[1]["config"].response_schema is None
    assert "JSON schema" in calls[1]["contents"][0]
    assert calls[0]["contents"][1].inline_data.data == b"original-image"
    assert calls[1]["contents"][1].inline_data.data == b"original-image"


def test_rate_limit_maps_to_429_and_retry_after(monkeypatch):
    quota_error = gemini_service.GeminiQuotaError(
        gemini_service.GeminiQuotaError.public_message
    )
    quota_error.retry_after = "15"

    def rate_limited(_image):
        raise quota_error

    monkeypatch.setattr(
        prescriptions_router,
        "extract_prescription_draft",
        rate_limited,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/prescriptions/extract",
            files={"file": ("test.png", png_bytes(), "image/png")},
        )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "15"
    assert response.json() == {
        "detail": gemini_service.GeminiQuotaError.public_message,
    }


def test_mock_mode_returns_results_without_constructing_a_client(monkeypatch):
    monkeypatch.setenv("USE_MOCK_AI", "true")

    def unexpected_client(**_kwargs):
        raise AssertionError("Gemini client must not be created in mock mode")

    monkeypatch.setattr(gemini_service.genai, "Client", unexpected_client)

    prescription = gemini_service.extract_prescription(b"image", "image/png")
    package = gemini_service.extract_package(b"image", "image/png")

    assert prescription.medicines[1].needs_review is True
    assert package.needs_review is True
