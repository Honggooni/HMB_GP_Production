"""Validate Seedance image references before upload or paid submission.

This module only inspects supplied bytes. It never edits an original file,
downloads a URL, changes Pillow's process-wide limits, or resizes media.
"""

from __future__ import annotations

import math
import re
import struct
from io import BytesIO
from typing import Any


MAX_IMAGE_PIXELS = 36_000_000
MAX_IMAGE_BYTES = 30 * 1024 * 1024

_MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp",
         "BMP": "image/bmp", "GIF": "image/gif", "TIFF": "image/tiff",
         "HEIF": "image/heif", "HEIC": "image/heic"}
_JPEG_SOF = frozenset((0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                       0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF))


class SeedanceImageLimitError(ValueError):
    """A bounded, public error without a source path or reference URL."""

    def __init__(self, code: str, message: str, details: dict[str, Any]) -> None:
        self.code = code
        self.details = details
        super().__init__(f"[{code}] {message}")


def _reference_label(media_name: Any, reference_ordinal: Any) -> str:
    try:
        ordinal = max(1, min(int(reference_ordinal), 50))
    except (ValueError, TypeError, OverflowError):
        ordinal = 1
    name = str(media_name or "")
    if re.search(r"(?i)(?:https?://|ftp://|file://|data:|authorization|bearer|api[_-]?key|password|secret)", name):
        name = ""
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).replace("\\", "/").rsplit("/", 1)[-1][:128]
    return f"Image reference {ordinal}" + (f" ({name})" if name else "")


def suggested_seedance_image_dimensions(width: int, height: int,
                                        *, max_pixels: int = MAX_IMAGE_PIXELS) -> tuple[int, int]:
    """Suggest a bounded size; retain an exact ratio when integer scaling fits."""
    if (isinstance(width, bool) or isinstance(height, bool) or isinstance(max_pixels, bool)
            or not isinstance(width, int) or not isinstance(height, int)
            or not isinstance(max_pixels, int) or width <= 0 or height <= 0 or max_pixels <= 0):
        raise ValueError("Image dimensions and pixel limit must be positive integers.")
    if width * height <= max_pixels:
        return width, height
    divisor = math.gcd(width, height)
    ratio_width, ratio_height = width // divisor, height // divisor
    factor = math.isqrt(max_pixels // (ratio_width * ratio_height))
    if divisor > 1 and factor > 0:
        return ratio_width * factor, ratio_height * factor
    scale = math.sqrt(max_pixels / (width * height))
    # Prefer even transport dimensions when possible. Original files are untouched.
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    if new_width > 1:
        new_width -= new_width % 2
    if new_height > 1:
        new_height -= new_height % 2
    if new_width * new_height > max_pixels:
        new_height = max(1, max_pixels // new_width)
    if new_width * new_height > max_pixels:
        new_width = max(1, max_pixels // new_height)
    return new_width, new_height


def _header_dimensions(data: bytes) -> tuple[str, int, int]:
    """Read bounded PNG/JPEG/WebP headers before allocating decoded pixels."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 33 or data[8:16] != b"\x00\x00\x00\rIHDR":
            raise ValueError("Invalid PNG header.")
        width, height = struct.unpack_from(">II", data, 16)
        return "PNG", width, height
    if data.startswith(b"\xff\xd8"):
        offset = 2
        while offset < len(data):
            if data[offset] != 0xFF:
                raise ValueError("Invalid JPEG marker.")
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD9, 0xDA):
                break
            if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            length = struct.unpack_from(">H", data, offset)[0]
            if length < 2 or offset + length > len(data):
                raise ValueError("Invalid JPEG segment length.")
            if marker in _JPEG_SOF:
                if length < 8:
                    raise ValueError("Invalid JPEG frame header.")
                height, width = struct.unpack_from(">HH", data, offset + 3)
                return "JPEG", width, height
            offset += length
        raise ValueError("JPEG frame dimensions are unavailable.")
    if data.startswith(b"RIFF") and len(data) >= 20 and data[8:12] == b"WEBP":
        riff_end = struct.unpack_from("<I", data, 4)[0] + 8
        if riff_end != len(data):
            raise ValueError("Invalid WebP container length.")
        offset = 12
        while offset + 8 <= riff_end:
            kind = data[offset:offset + 4]
            length = struct.unpack_from("<I", data, offset + 4)[0]
            start = offset + 8
            end = start + length
            if end > riff_end:
                raise ValueError("Invalid WebP chunk length.")
            if kind == b"VP8X":
                if length != 10:
                    raise ValueError("Invalid extended WebP dimensions.")
                return ("WEBP", 1 + int.from_bytes(data[start + 4:start + 7], "little"),
                        1 + int.from_bytes(data[start + 7:start + 10], "little"))
            if kind == b"VP8L":
                if length < 5 or data[start] != 0x2F:
                    raise ValueError("Invalid lossless WebP dimensions.")
                bits = struct.unpack_from("<I", data, start + 1)[0]
                return "WEBP", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if kind == b"VP8 ":
                if length < 10 or data[start + 3:start + 6] != b"\x9d\x01\x2a":
                    raise ValueError("Invalid lossy WebP frame dimensions.")
                width, height = struct.unpack_from("<HH", data, start + 6)
                return "WEBP", width & 0x3FFF, height & 0x3FFF
            offset = end + (length % 2)
        raise ValueError("WebP frame dimensions are unavailable.")
    if data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 10:
        width, height = struct.unpack_from("<HH", data, 6)
        return "GIF", width, height
    if data.startswith(b"BM") and len(data) >= 26:
        dib_size = struct.unpack_from("<I", data, 14)[0]
        if dib_size == 12:
            width, height = struct.unpack_from("<HH", data, 18)
        elif dib_size >= 40:
            width, height = struct.unpack_from("<ii", data, 18)
            height = abs(height)
        else:
            raise ValueError("Invalid BMP dimensions.")
        return "BMP", width, height
    # Preserve the existing TIFF/HEIF input contract. Decoder metadata is read
    # before pixel allocation; the same limit applies before verify/load below.
    if (data.startswith((b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"))
            or (len(data) >= 12 and data[4:8] == b"ftyp")):
        from PIL import Image
        with Image.open(BytesIO(data)) as opened:
            if opened.format not in {"TIFF", "HEIF", "HEIC"}:
                raise ValueError("Unsupported image format.")
            return opened.format, *opened.size
    raise ValueError("Unsupported image reference format.")


def inspect_seedance_image_payload(data: bytes | bytearray, *, media_name: str = "",
                                    reference_ordinal: int = 1) -> dict[str, Any]:
    """Validate actual encoded media and return dimensions before transport."""
    return _inspect_image(data, media_name=media_name, reference_ordinal=reference_ordinal,
                          max_pixels=MAX_IMAGE_PIXELS, max_bytes=MAX_IMAGE_BYTES)


def _inspect_image(data: bytes | bytearray, *, media_name: str, reference_ordinal: int,
                   max_pixels: int, max_bytes: int) -> dict[str, Any]:
    label = _reference_label(media_name, reference_ordinal)
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise SeedanceImageLimitError("SEEDANCE_IMAGE_INVALID", f"{label} has no encoded image bytes.", {})
    size = len(data)
    # Preserve the existing transport contract: encoded image bytes must be < 30 MiB.
    if size >= max_bytes:
        raise SeedanceImageLimitError("SEEDANCE_IMAGE_BYTE_LIMIT",
                                      f"{label} contains {size:,} bytes; must be smaller than {max_bytes:,} bytes.",
                                      {"bytes": size, "max_bytes_exclusive": max_bytes})
    value = bytes(data)
    try:
        format_name, width, height = _header_dimensions(value)
        if width <= 0 or height <= 0:
            raise ValueError("Image dimensions must be positive.")
    except ImportError as exc:
        raise SeedanceImageLimitError("SEEDANCE_IMAGE_VALIDATOR_UNAVAILABLE",
                                      f"{label} cannot be validated because its image decoder is unavailable.", {}) from exc
    except Exception as exc:
        raise SeedanceImageLimitError("SEEDANCE_IMAGE_INVALID",
                                      f"{label} is not a valid supported image.", {}) from exc
    pixels = width * height
    dimensions = {"width": width, "height": height, "pixels": pixels,
                  "max_pixels": max_pixels, "bytes": size}
    if pixels > max_pixels:
        suggested_width, suggested_height = suggested_seedance_image_dimensions(width, height, max_pixels=max_pixels)
        dimensions.update(suggested_width=suggested_width, suggested_height=suggested_height)
        raise SeedanceImageLimitError("SEEDANCE_IMAGE_PIXEL_LIMIT",
                                      f"{label} is {width}x{height} = {pixels:,} pixels; maximum {max_pixels:,} pixels. "
                                      f"Use a copy at {suggested_width}x{suggested_height} or smaller. Original media was not changed.",
                                      dimensions)
    try:
        from PIL import Image

        # Check decoder/header agreement, then decode one bounded image to reject
        # truncated/corrupt media. Never alter Image.MAX_IMAGE_PIXELS globally.
        with Image.open(BytesIO(value)) as opened:
            if opened.format != format_name or opened.size != (width, height):
                raise ValueError("Image header and decoder dimensions differ.")
            opened.verify()
        with Image.open(BytesIO(value)) as opened:
            opened.load()
    except ImportError as exc:
        raise SeedanceImageLimitError("SEEDANCE_IMAGE_VALIDATOR_UNAVAILABLE",
                                      f"{label} cannot be validated because its image decoder is unavailable.", dimensions) from exc
    except Exception as exc:
        raise SeedanceImageLimitError("SEEDANCE_IMAGE_INVALID",
                                      f"{label} could not be decoded as a valid {format_name} image.", dimensions) from exc
    return {"format": format_name, "mime_type": _MIME[format_name],
            "width": width, "height": height, "pixels": pixels, "bytes": size}
