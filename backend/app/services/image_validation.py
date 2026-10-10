"""Validation for uploaded prescription and medicine-package images."""

from __future__ import annotations

import warnings
from io import BytesIO
from dataclasses import dataclass

from PIL import Image, ImageOps, ImageStat, ImageFilter, UnidentifiedImageError


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


MAX_PACKAGING_REQUEST_SIZE = 12 * 1024 * 1024
MAX_ANALYSIS_IMAGES = 3
MAX_PREPARED_SIDE = 2200


@dataclass
class PreparedPackageImage:
    data: bytes
    mime_type: str
    quality: dict


def prepare_package_image(image_bytes: bytes, index: int, role: str) -> PreparedPackageImage:
    """Decode fully, correct orientation and resize; never reconstruct evidence."""
    validate_image(image_bytes)
    try:
        with Image.open(BytesIO(image_bytes)) as original:
            original.load()
            if getattr(original, 'n_frames', 1) != 1:
                raise ImageValidationError('Animated images are not supported')
            oriented = ImageOps.exif_transpose(original)
            if oriented.mode in {'RGBA', 'LA'} or 'transparency' in oriented.info:
                rgba = oriented.convert('RGBA')
                image = Image.new('RGB', rgba.size, 'white')
                image.paste(rgba, mask=rgba.getchannel('A'))
            else:
                image = oriented.convert('RGB')
            width, height = image.size
            sample = image.copy()
            sample.thumbnail((512, 512))
            gray = sample.convert('L')
            stats = ImageStat.Stat(gray)
            brightness, contrast = stats.mean[0], stats.stddev[0]
            # Edge variance is a conservative focus hint, not a calibrated OCR score.
            interior = gray.filter(ImageFilter.FIND_EDGES).crop((1, 1, max(2, gray.width - 1), max(2, gray.height - 1)))
            edge_variance = ImageStat.Stat(interior).var[0]
            histogram = gray.histogram()
            white_fraction = sum(histogram[250:]) / max(1, sample.width * sample.height)
            issues = []
            if min(width, height) < 300:
                issues.append('Low resolution: capture a larger, focused label photo.')
            if brightness < 35:
                issues.append('Very dark photo: use even lighting.')
            if contrast < 12:
                issues.append('Low contrast: printed text may be hard to read.')
            if edge_variance < 20:
                issues.append('Few sharp edges: check focus and label legibility.')
            if brightness > 235 and white_fraction > .85:
                issues.append('Mostly bright areas: check for glare or an empty frame.')
            unusable = min(width, height) < 100 or brightness < 12 or (contrast < 3 and edge_variance < 5)
            image.thumbnail((MAX_PREPARED_SIDE, MAX_PREPARED_SIDE), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format='JPEG', quality=92)
    except ImageValidationError:
        raise
    except (OSError, ValueError, SyntaxError) as exc:
        raise ImageValidationError('Invalid or corrupt PNG/JPEG image') from exc
    return PreparedPackageImage(output.getvalue(), 'image/jpeg', {
        'image_index': index, 'role': role, 'width': width, 'height': height,
        'brightness': round(brightness, 2), 'contrast': round(contrast, 2),
        'edge_variance': round(edge_variance, 2), 'issues': issues, 'unusable': unusable,
    })
