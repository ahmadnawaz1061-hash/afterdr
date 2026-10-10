"""Redacted live diagnostics for the After Dr Gemini integration."""

from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, ImageDraw


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

from app.services.gemini_service import extract_prescription  # noqa: E402


def safe_error(exc: Exception, api_key: str) -> str:
    message = str(exc)
    if api_key:
        message = message.replace(api_key, "<redacted>")
    return f"{type(exc).__name__}: {message}"


def diagnostic_png() -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", (480, 180), "white")
    ImageDraw.Draw(image).text(
        (20, 20),
        "Demo prescription\nMedicine: Demo Relief One\nStrength: 500 mg",
        fill="black",
    )
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> int:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "").strip()
    use_mock = os.getenv("USE_MOCK_AI", "").strip()
    print(f"key_set={bool(api_key)} key_length={len(api_key)}")
    print(f"model={model or '<unset>'}")
    print(f"USE_MOCK_AI={use_mock or '<unset>'}")

    if not api_key:
        print("client_setup: GeminiConfigurationError: GEMINI_API_KEY is not set")
        return 1

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=45_000),
    )

    try:
        models = list(client.models.list())
        print(f"model_list: OK count={len(models)}")
        for item in models:
            print(f"  {getattr(item, 'name', '<unnamed>')}")
    except Exception as exc:
        print(f"model_list: FAILED {safe_error(exc, api_key)}")

    try:
        response = client.models.generate_content(
            model=model.removeprefix("models/"),
            contents="Reply with exactly: Gemini text diagnostic OK",
        )
        print(f"text_call: OK text_present={bool(response.text)}")
    except Exception as exc:
        print(f"text_call: FAILED {safe_error(exc, api_key)}")

    try:
        result = extract_prescription(diagnostic_png(), "image/png")
        print(
            "image_call: OK "
            f"medicine_count={len(result.medicines)} "
            f"patient_name_present={bool(result.patient_name)}"
        )
    except Exception as exc:
        print(f"image_call: FAILED {safe_error(exc, api_key)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
