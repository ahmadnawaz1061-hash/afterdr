"""Validation for uploaded prescription and medicine-package images."""

from __future__ import annotations

import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError


MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_IMAGE_WIDTH = 6000
MAX_IMAGE_HEIGHT = 6000
SUPPORTED_FORMATS = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
}


class ImageValidationError(ValueError):
    """Raised when uploaded bytes are not an acceptable image."""


class ImageTooLargeError(ImageValidationError):
    """Raised when an upload exceeds the byte limit."""


class ImageDimensionsError(ImageValidationError):
    """Raised when decoded dimensions exceed processing limits."""


def validate_image(image_bytes: bytes) -> str:
    """Validate PNG/JPEG bytes and return their content-derived MIME type."""
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise ImageTooLargeError("Image exceeds the 5 MB limit")
    if not image_bytes:
        raise ImageValidationError("Image is empty")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as image:
                detected_format = image.format
                if detected_format not in SUPPORTED_FORMATS:
                    raise ImageValidationError("Only PNG and JPEG images are supported")

                width, height = image.size
                if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
                    raise ImageDimensionsError(
                        f"Image dimensions exceed {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT} pixels"
                    )
                image.verify()
    except ImageValidationError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise ImageValidationError("Invalid or corrupt PNG/JPEG image") from exc

    return SUPPORTED_FORMATS[detected_format]
