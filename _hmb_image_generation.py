"""Provider-neutral image generation contract, with no provider credentials.

Importing this module is offline. The existing authenticated Broker bridge is
loaded only when a transport is requested. Image generation is available only
after the server advertises this exact contract and its registered models.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass, replace, field
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterable
from urllib.parse import quote
import urllib.error
import urllib.request
from uuid import uuid4
import warnings

import _hmb_broker_config as broker_config
import _hmb_queue_admission as queue

CAPABILITIES_SCHEMA = "hmb-image-generation-capabilities-v1"
JOB_SCHEMA = "hmb-image-generation-job-v1"
GOOGLE_NATIVE_CONTRACT = "google-native-image-v1"
MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_PIXELS = 64 * 1024 * 1024
MAX_PROMPT_LENGTH = 32768
MAX_RESIZE_INPUT_BYTES = 4 * MAX_IMAGE_BYTES
JOB_SUCCESS_STATUSES = frozenset({"succeeded"})
JOB_FAILURE_STATUSES = frozenset({"failed", "cancelled", "expired"})
JOB_PENDING_STATUSES = frozenset({"queued", "running"})
_MIME_FORMATS = {"image/png": "png", "image/jpeg": "jpeg", "image/webp": "webp"}
_EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")
_TASKS = frozenset({"text-to-image", "image-to-image"})
OPTION_SCHEMA = "hmb-image-model-options-v1"
_OPTION_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_OPTION_TYPES = frozenset({"boolean", "integer", "number", "string"})
_DEFAULT_FIELDS = {"task": "tasks", "ratio": "aspect_ratios", "image_size": "image_sizes", "output_format": "output_formats"}


def _finite_number(value: Any) -> bool:
    if type(value) not in {int, float}:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


class ImageGenerationError(RuntimeError):
    def __init__(self, message: str, *, code: str = "IMAGE_GENERATION_ERROR",
                 submission_outcome_unknown: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.submission_outcome_unknown = submission_outcome_unknown


def _fail(message: str, code: str = "INVALID_IMAGE_GENERATION_CONTRACT") -> None:
    raise ImageGenerationError(message, code=code)


def _text(value: Any, name: str, *, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(
        ord(character) < 32 for character in value
    ):
        _fail(f"Image generation {name} is invalid.")
    return value.strip()


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        _fail(f"Image generation {name} is invalid.")
    return value


def _strings(value: Any, name: str, *, allowed: frozenset[str] | None = None) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > 64:
        _fail(f"Image generation {name} is invalid.")
    values = tuple(_text(item, name, limit=128) for item in value)
    if len(set(values)) != len(values) or (allowed is not None and not set(values) <= allowed):
        _fail(f"Image generation {name} is invalid.")
    return values


@dataclass(frozen=True)
class ImageOption:
    name: str
    type: str
    label: str
    default: bool | int | float | str
    choices: tuple[bool | int | float | str, ...] = ()
    minimum: int | float | None = None
    maximum: int | float | None = None
    step: int | float | None = None
    max_length: int | None = None


def _option_value(spec: ImageOption, value: Any) -> bool | int | float | str:
    kind = spec.type
    valid = (type(value) is bool if kind == "boolean" else type(value) is int and _finite_number(value) if kind == "integer" else
             _finite_number(value) if kind == "number" else isinstance(value, str))
    if not valid:
        _fail(f"Image model option '{spec.name}' has the wrong value type.", "IMAGE_OPTION_INVALID")
    if kind in {"integer", "number"}:
        if ((spec.minimum is not None and value < spec.minimum) or (spec.maximum is not None and value > spec.maximum)):
            _fail(f"Image model option '{spec.name}' is outside its supported range.", "IMAGE_OPTION_INVALID")
        if spec.step is not None:
            from decimal import Decimal
            quotient = (Decimal(str(value)) - Decimal(str(spec.minimum if spec.minimum is not None else 0))) / Decimal(str(spec.step))
            if abs(quotient - quotient.to_integral_value()) > Decimal("0.00000001"):
                _fail(f"Image model option '{spec.name}' does not match its supported step.", "IMAGE_OPTION_INVALID")
    if kind == "string" and (len(value) > (spec.max_length if spec.max_length is not None else 1024) or "\x00" in value):
        _fail(f"Image model option '{spec.name}' exceeds its text limit.", "IMAGE_OPTION_INVALID")
    if spec.choices and value not in spec.choices:
        _fail(f"Image model option '{spec.name}' is not a supported choice.", "IMAGE_OPTION_INVALID")
    return value


def parse_option_spec(name: str, descriptor: Any) -> ImageOption:
    allowed = {"type", "label", "default", "enum", "minimum", "maximum", "step", "max_length"}
    if (not isinstance(name, str) or _OPTION_NAME.fullmatch(name) is None or not isinstance(descriptor, dict)
            or set(descriptor) - allowed or not isinstance(descriptor.get("type"), str)
            or descriptor["type"] not in _OPTION_TYPES or "default" not in descriptor):
        _fail("Image model option descriptor is unsupported.", "IMAGE_OPTION_SCHEMA_INVALID")
    kind = descriptor["type"]
    label = _text(descriptor.get("label", name), "option label", limit=128)
    numeric: dict[str, int | float | None] = {}
    for key in ("minimum", "maximum", "step"):
        value = descriptor.get(key)
        if key in descriptor and (kind not in {"number", "integer"} or not _finite_number(value)
                or (kind == "integer" and type(value) is not int)):
            _fail("Image model option range is invalid.", "IMAGE_OPTION_SCHEMA_INVALID")
        numeric[key] = value
    if (numeric["minimum"] is not None and numeric["maximum"] is not None and numeric["minimum"] > numeric["maximum"]
            or numeric["step"] is not None and numeric["step"] <= 0):
        _fail("Image model option range is invalid.", "IMAGE_OPTION_SCHEMA_INVALID")
    max_length = descriptor.get("max_length")
    if "max_length" in descriptor and (kind != "string" or type(max_length) is not int or not 0 <= max_length <= 4096):
        _fail("Image model option text limit is invalid.", "IMAGE_OPTION_SCHEMA_INVALID")
    choices = descriptor.get("enum", [])
    if not isinstance(choices, list) or ("enum" in descriptor and not choices) or len(choices) > 64:
        _fail("Image model option choices are invalid.", "IMAGE_OPTION_SCHEMA_INVALID")
    spec = ImageOption(name, kind, label, descriptor["default"], tuple(choices), **numeric, max_length=max_length)
    # Validate defaults and choices with the same strict scalar/range rules as
    # submitted values; bool must never pass as integer zero/one.
    without_choices = ImageOption(name, kind, label, descriptor["default"], **numeric, max_length=max_length)
    for value in choices:
        _option_value(without_choices, value)
    if len(set(choices)) != len(choices):
        _fail("Image model option choices are duplicated.", "IMAGE_OPTION_SCHEMA_INVALID")
    _option_value(spec, descriptor["default"])
    return spec


def serialize_option_spec(spec: ImageOption) -> dict[str, Any]:
    result: dict[str, Any] = {"type": spec.type, "label": spec.label, "default": spec.default}
    if spec.choices:
        result["enum"] = list(spec.choices)
    for key in ("minimum", "maximum", "step", "max_length"):
        value = getattr(spec, key)
        if value is not None:
            result[key] = value
    # Reuse the parser so a forged cache/spec cannot serialize unchecked values.
    parse_option_spec(spec.name, result)
    return result


def parse_option_schema(raw: Any) -> tuple[str, tuple[ImageOption, ...]]:
    if (not isinstance(raw, dict) or set(raw) != {"schema", "revision", "properties"}
            or raw.get("schema") != OPTION_SCHEMA or not isinstance(raw.get("properties"), dict)
            or len(raw["properties"]) > 32):
        _fail("Image model options schema is unsupported.", "IMAGE_OPTION_SCHEMA_INVALID")
    revision = _text(raw.get("revision"), "option schema revision", limit=128)
    return revision, tuple(parse_option_spec(name, value) for name, value in raw["properties"].items())


def serialize_option_schema(revision: str, options: Iterable[ImageOption]) -> dict[str, Any]:
    options = tuple(options)
    if len(options) > 32 or len({spec.name for spec in options}) != len(options):
        _fail("Image model options schema is invalid.", "IMAGE_OPTION_SCHEMA_INVALID")
    result = {"schema": OPTION_SCHEMA, "revision": revision,
              "properties": {spec.name: serialize_option_spec(spec) for spec in options}}
    parse_option_schema(result)
    return result


@dataclass(frozen=True)
class ImageModelCapability:
    provider: str
    model_id: str
    display_name: str
    enabled: bool
    credential_ready: bool
    tasks: tuple[str, ...]
    aspect_ratios: tuple[str, ...]
    image_sizes: tuple[str, ...]
    output_formats: tuple[str, ...]
    max_reference_images: int
    max_reference_bytes: int
    option_schema_revision: str = ""
    options: tuple[ImageOption, ...] = ()
    defaults: tuple[tuple[str, str], ...] = ()
    provider_request_contract: str = ""
    max_reference_image_bytes: int = 0
    max_result_images: int = 1
    _native_contract_json: str = field(default="null", repr=False)
    _legacy_profile_json: str = field(default="{}", repr=False)

    @property
    def native_contract(self) -> dict[str, Any] | None:
        return json.loads(self._native_contract_json)


@dataclass(frozen=True)
class ImageCapabilities:
    enabled: bool
    models: tuple[ImageModelCapability, ...]
    client_request_lookup: bool = False
    persistence_scope: str = "personal_local"
    max_request_bytes: int = MAX_REQUEST_BYTES
    _queue_admission: Any = field(default=None, repr=False, compare=False)


def model_defaults(model: ImageModelCapability) -> dict[str, str]:
    return dict(model.defaults)


def _with_native_google_contract(model: ImageModelCapability, raw: dict[str, Any]) -> ImageModelCapability:
    marker = raw.get("provider_request_contract", "")
    if not marker:
        return model
    _identifier(marker, "provider request contract")
    if marker != GOOGLE_NATIVE_CONTRACT:
        return replace(model, provider_request_contract=marker)
    if model.provider != "google" or model.model_id not in {"gemini-3-pro-image", "gemini-3.1-flash-image"}:
        _fail("The native Google contract belongs to a different model.", "IMAGE_OPTION_SCHEMA_INVALID")
    native = raw.get("native_contract")
    if not isinstance(native, dict):
        _fail("The Broker native Google contract is missing.", "IMAGE_OPTION_SCHEMA_INVALID")
    formats = _strings(native.get("output_formats"), "native output formats", allowed=frozenset({"native"}))
    revision, options = parse_option_schema(native.get("option_schema"))
    defaults = native.get("defaults")
    choices = {"task": model.tasks, "ratio": model.aspect_ratios, "image_size": model.image_sizes, "output_format": formats}
    if (not isinstance(defaults, dict) or set(defaults) - set(choices)
            or any(not isinstance(value, str) or value not in choices[name] for name, value in defaults.items())):
        _fail("The native Google defaults are invalid.", "IMAGE_OPTION_SCHEMA_INVALID")
    per_image, combined, results = (native.get(name) for name in (
        "max_reference_image_bytes", "max_reference_bytes", "max_result_images"))
    if (type(per_image) is not int or not 1 <= per_image <= MAX_IMAGE_BYTES
            or type(combined) is not int or not 1 <= combined <= MAX_IMAGE_BYTES
            or type(results) is not int or not 1 <= results <= 128):
        _fail("The native Google media limits are invalid.", "IMAGE_OPTION_SCHEMA_INVALID")
    # Retain only validated descriptors. This cache is an offline UI hint and
    # can never replace fresh Broker capabilities at the create boundary.
    checked = {"output_formats": list(formats), "defaults": dict(defaults),
        "option_schema": serialize_option_schema(revision, options),
        "max_reference_image_bytes": per_image, "max_reference_bytes": combined, "max_result_images": results}
    legacy = {name: deepcopy(raw[name]) for name in ("provider", "model_id", "display_name", "enabled", "credential_ready",
        "tasks", "aspect_ratios", "image_sizes", "output_formats", "max_reference_images", "max_reference_bytes")}
    for name in ("defaults", "option_schema"):
        if name in raw:
            legacy[name] = deepcopy(raw[name])
    return replace(model, provider_request_contract=marker, output_formats=formats,
        option_schema_revision=revision, options=options, defaults=tuple(defaults.items()),
        max_reference_bytes=combined, max_reference_image_bytes=per_image, max_result_images=results,
        _native_contract_json=json.dumps(checked, ensure_ascii=False, allow_nan=False),
        _legacy_profile_json=json.dumps(legacy, ensure_ascii=False, allow_nan=False))


def parse_capabilities(raw: Any) -> ImageCapabilities:
    if (not isinstance(raw, dict) or raw.get("schema") != CAPABILITIES_SCHEMA
            or type(raw.get("version")) is not int or raw["version"] != 1
            or type(raw.get("enabled")) is not bool or raw.get("persistence_scope") != "personal_local"):
        _fail("This Broker does not advertise the image generation contract.", "IMAGE_GENERATION_UNSUPPORTED")
    models = raw.get("models")
    if not isinstance(models, list) or len(models) > 128:
        _fail("Image generation model catalogue is invalid.")
    parsed_models: list[ImageModelCapability] = []
    for item in models:
        if not isinstance(item, dict) or any(type(item.get(name)) is not bool for name in ("enabled", "credential_ready")):
            _fail("Image generation model readiness is invalid.")
        count, byte_limit = item.get("max_reference_images"), item.get("max_reference_bytes")
        if (type(count) is not int or not 0 <= count <= 64 or type(byte_limit) is not int
                or not 0 <= byte_limit <= MAX_IMAGE_BYTES or (count > 0 and byte_limit == 0)):
            _fail("Image generation reference limits are invalid.")
        revision, options = parse_option_schema(item["option_schema"]) if "option_schema" in item else ("", ())
        defaults = item.get("defaults", {})
        if (not isinstance(defaults, dict) or set(defaults) - set(_DEFAULT_FIELDS)
                or any(not isinstance(value, str) or value not in item.get(_DEFAULT_FIELDS[key], []) for key, value in defaults.items())):
            _fail("Image generation model defaults are invalid.")
        model = ImageModelCapability(
            _identifier(item.get("provider"), "provider"), _identifier(item.get("model_id"), "model"),
            _text(item.get("display_name"), "model name"), item["enabled"], item["credential_ready"],
            _strings(item.get("tasks"), "tasks", allowed=_TASKS),
            _strings(item.get("aspect_ratios"), "aspect ratios"), _strings(item.get("image_sizes"), "image sizes"),
            _strings(item.get("output_formats"), "output formats", allowed=frozenset(_MIME_FORMATS.values())),
            count, byte_limit, revision, options, tuple(defaults.items()))
        parsed_models.append(_with_native_google_contract(model, item))
    if len({(item.provider, item.model_id) for item in parsed_models}) != len(parsed_models):
        _fail("Image generation models are duplicated.")
    lookup = raw.get("client_request_lookup", False)
    if type(lookup) is not bool:
        _fail("Image generation recovery capability is invalid.")
    request_limit = raw.get("max_request_bytes", MAX_REQUEST_BYTES)
    if type(request_limit) is not int or not 1 <= request_limit <= 2**31 - 1:
        _fail("Image generation request byte limit is invalid.")
    return ImageCapabilities(raw["enabled"], tuple(parsed_models), lookup, max_request_bytes=request_limit)


def _builtin_google_profile(model_id: str, display_name: str, ratios: tuple[str, ...], sizes: tuple[str, ...],
                            *, image_search: bool = False) -> ImageModelCapability:
    descriptors: dict[str, dict[str, Any]] = {
        "temperature": {"type": "number", "label": "Temperature", "default": 1.0, "minimum": 0, "maximum": 2, "step": 0.1},
        "top_p": {"type": "number", "label": "Top P", "default": 0.95, "minimum": 0, "maximum": 1, "step": 0.05},
        "use_google_search": {"type": "boolean", "label": "Google Search", "default": False},
    }
    if image_search:
        descriptors["use_google_image_search"] = {"type": "boolean", "label": "Google Image Search", "default": False}
    return ImageModelCapability("google", model_id, display_name, False, False,
        ("text-to-image", "image-to-image"), ratios, sizes, ("png",), 14, 12 * 1024 * 1024,
        "builtin-native-google-v1", tuple(parse_option_spec(key, value) for key, value in descriptors.items()),
        (("task", "text-to-image"), ("ratio", "16:9"), ("image_size", "1K"), ("output_format", "png")))


# Offline authoring hints matching the installed native Google image node.
# They never authorize a request: actual Broker capabilities/readiness remain
# mandatory, and the client must not send this built-in revision as server proof.
BUILTIN_IMAGE_MODEL_PROFILES = (
    _builtin_google_profile("gemini-3-pro-image", "Nano Banana Pro",
        ("1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"), ("1K", "2K", "4K")),
    _builtin_google_profile("gemini-3.1-flash-image", "Nano Banana 2",
        ("1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"),
        ("512", "1K", "2K", "4K"), image_search=True),
)


@dataclass(frozen=True)
class ImageInvocation:
    client_request_id: str
    provider: str
    model_id: str
    _payload_json: str
    _queue_admission: Any = field(default=None, repr=False)
    _queue_headers_json: str = "{}"

    def payload(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


@dataclass(frozen=True)
class ValidatedImage:
    data: bytes
    mime_type: str
    width: int
    height: int
    sha256: str


@dataclass(frozen=True)
class SavedImage:
    path: Path
    mime_type: str
    width: int
    height: int
    sha256: str


def validate_image_bytes(data: bytes, *, advertised_mime: str = "", advertised_sha256: str = "",
                         max_bytes: int = MAX_IMAGE_BYTES) -> ValidatedImage:
    if not isinstance(data, bytes) or not data or len(data) > min(max_bytes, MAX_IMAGE_BYTES):
        _fail("Image is empty or exceeds the byte limit.", "IMAGE_LIMIT")
    if advertised_mime and advertised_mime not in _MIME_FORMATS:
        _fail("Image MIME type is unsupported.", "INVALID_IMAGE")
    try:
        from PIL import Image
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                image_format, width, height = str(image.format).lower(), image.width, image.height
                if image_format == "jpg":
                    image_format = "jpeg"
                if (image_format not in _MIME_FORMATS.values() or width <= 0 or height <= 0
                        or width * height > MAX_IMAGE_PIXELS or getattr(image, "n_frames", 1) != 1):
                    _fail("Image dimensions or format are unsupported.", "INVALID_IMAGE")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except ImageGenerationError:
        raise
    except Exception as exc:
        raise ImageGenerationError("Image bytes could not be decoded as PNG, JPEG or WebP.", code="INVALID_IMAGE") from exc
    mime = next(key for key, value in _MIME_FORMATS.items() if value == image_format)
    if advertised_mime and advertised_mime != mime:
        _fail("Image bytes do not match their advertised MIME type.", "INVALID_IMAGE")
    digest = hashlib.sha256(data).hexdigest()
    if advertised_sha256 and (re.fullmatch(r"[a-fA-F0-9]{64}", advertised_sha256) is None
                              or advertised_sha256.lower() != digest):
        _fail("Image checksum did not match the Broker result.", "INVALID_IMAGE")
    return ValidatedImage(data, mime, width, height, digest)


def _reference_data(value: Any, *, max_bytes: int) -> ValidatedImage:
    if not isinstance(value, (str, bytes, Path, dict)) and hasattr(value, "value"):
        value = value.value
    if isinstance(value, dict):
        candidates = [value[key] for key in ("value", "image_url", "url", "path") if key in value]
        if len(candidates) != 1:
            _fail("Reference image needs one local file or data URI.", "INVALID_REFERENCE")
        value = candidates[0]
    if isinstance(value, bytes):
        return validate_image_bytes(value, max_bytes=max_bytes)
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str) or not value:
        _fail("Reference image needs a local file or data URI.", "INVALID_REFERENCE")
    if value.startswith("data:"):
        if len(value) > ((max_bytes + 2) // 3) * 4 + 128:
            _fail("Reference image exceeds the byte limit.", "IMAGE_LIMIT")
        match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]*={0,2})", value)
        if match is None:
            _fail("Reference image data URI is invalid.", "INVALID_REFERENCE")
        try:
            raw = base64.b64decode(match[2], validate=True)
        except ValueError as exc:
            raise ImageGenerationError("Reference image encoding is invalid.", code="INVALID_REFERENCE") from exc
        return validate_image_bytes(raw, advertised_mime=match[1], max_bytes=max_bytes)
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value) or value.startswith("file:"):
        _fail("Remote reference URLs must be resolved by the local loader first.", "INVALID_REFERENCE")
    try:
        with Path(value).open("rb") as stream:
            data = stream.read(max_bytes + 1)
    except (OSError, ValueError) as exc:
        raise ImageGenerationError("Reference image file could not be read.", code="INVALID_REFERENCE") from exc
    return validate_image_bytes(data, max_bytes=max_bytes)


def _shrink_reference(image: ValidatedImage, byte_limit: int) -> ValidatedImage:
    """Best effort local, bounded, aspect-preserving resize of decoded bytes."""
    if len(image.data) <= byte_limit:
        return image
    from PIL import Image
    with Image.open(io.BytesIO(image.data)) as source:
        source.load()
        if source.mode not in {"RGB", "RGBA", "L", "LA"}:
            source = source.convert("RGBA" if "transparency" in source.info else "RGB")
        if image.mime_type == "image/jpeg" and source.mode not in {"RGB", "L"}:
            source = source.convert("RGB")
        size = source.size
        for attempt in range(12):
            # First try better packing without losing pixel dimensions. Later
            # passes reduce both dimensions together, never cropping/stretching.
            if attempt:
                factor = min(0.85, max(0.1, math.sqrt(byte_limit / max(1, encoded_size)) * 0.9))
                smaller = (max(1, int(size[0] * factor)), max(1, int(size[1] * factor)))
                if smaller == size:
                    break
                size = smaller
            resized = source if size == source.size else source.resize(size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            if image.mime_type == "image/jpeg":
                resized.save(buffer, "JPEG", quality=85, optimize=True)
            elif image.mime_type == "image/webp":
                resized.save(buffer, "WEBP", quality=85, method=4)
            else:
                resized.save(buffer, "PNG", optimize=True, compress_level=9)
            result = buffer.getvalue()
            encoded_size = len(result)
            if encoded_size <= byte_limit:
                return validate_image_bytes(result, advertised_mime=image.mime_type)
    _fail("Reference images could not fit this model's byte budget after local resize.", "IMAGE_LIMIT")


def _shrink_native_reference(image: ValidatedImage, byte_limit: int) -> ValidatedImage:
    """Use Standard's lossless-first WebP strategy, on a worker thread."""
    if len(image.data) <= byte_limit:
        return image
    from PIL import Image
    with Image.open(io.BytesIO(image.data)) as source:
        source.load()
        if source.mode in {"P", "LA"}:
            source = source.convert("RGBA")
        buffer = io.BytesIO()
        source.save(buffer, format="WEBP", lossless=True, method=6)
        if len(buffer.getvalue()) <= byte_limit:
            return validate_image_bytes(buffer.getvalue(), advertised_mime="image/webp")
        for scale in (1.0, 0.75, 0.5):
            size = (max(1, int(source.width * scale)), max(1, int(source.height * scale)))
            resized = source if size == source.size else source.resize(size)
            for quality in (100, 95, 85):
                buffer = io.BytesIO()
                resized.save(buffer, format="WEBP", quality=quality, method=6)
                if len(buffer.getvalue()) <= byte_limit:
                    return validate_image_bytes(buffer.getvalue(), advertised_mime="image/webp")
    _fail("Input images could not fit the native image or Broker request byte budget. "
        "Use smaller references; no image was submitted.", "IMAGE_LIMIT")


def _validated_model_options(model: ImageModelCapability, supplied: Any) -> dict[str, Any]:
    if supplied is None:
        supplied = {}
    if not isinstance(supplied, dict) or len(supplied) > 32:
        _fail("Image model options must be a supported option dictionary.", "IMAGE_OPTION_INVALID")
    if not model.option_schema_revision:
        if supplied:
            _fail("This Broker has not advertised advanced options for the selected image model.", "IMAGE_OPTION_UNSUPPORTED")
        return {}
    allowed = {spec.name for spec in model.options}
    if set(supplied) - allowed:
        _fail("The selected model does not support one or more saved image options.", "IMAGE_OPTION_UNSUPPORTED")
    return {spec.name: _option_value(spec, supplied[spec.name] if spec.name in supplied else spec.default)
            for spec in model.options}


def prepare_invocation(capabilities: ImageCapabilities, *, model_id: str, provider: str = "",
                       task: str, prompt: str, ratio: str, image_size: str,
                       output_format: str, references: Iterable[Any] = (), client_request_id: str = "",
                       model_options: dict[str, Any] | None = None, auto_image_resize: bool = False,
                       provider_request_contract: str = "") -> ImageInvocation:
    admission = capabilities._queue_admission
    if admission is not None:
        admission.require("image")
    if not capabilities.enabled and admission is None:
        _fail("Image generation is not enabled on this Broker.", "IMAGE_GENERATION_UNAVAILABLE")
    models = [item for item in capabilities.models if item.model_id == model_id and (not provider or item.provider == provider)]
    if len(models) != 1:
        _fail("Select a model advertised by this Broker.", "IMAGE_MODEL_REQUIRED")
    model = models[0]
    if provider_request_contract:
        if (provider_request_contract != GOOGLE_NATIVE_CONTRACT
                or model.provider_request_contract != provider_request_contract):
            _fail("Update the Broker native Google image adapter before generating. No image was submitted.",
                  "IMAGE_NATIVE_CONTRACT_REQUIRED")
    elif output_format == "native":
        _fail("Native image output requires an advertised provider contract.", "IMAGE_NATIVE_CONTRACT_REQUIRED")
    if not model.enabled and admission is None:
        _fail("The selected image model is disabled on the Broker. Ask the server administrator to enable it.", "IMAGE_MODEL_DISABLED")
    if not model.credential_ready and admission is None:
        _fail("The selected image model credential is not ready. Ask the server administrator to check its provider API key.", "IMAGE_CREDENTIAL_NOT_READY")
    if task not in model.tasks or ratio not in model.aspect_ratios or image_size not in model.image_sizes or output_format not in model.output_formats:
        _fail("The selected image generation option is not supported by this model.", "IMAGE_OPTION_UNSUPPORTED")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_LENGTH or "\x00" in prompt:
        _fail("Enter an image prompt within the supported length.", "IMAGE_PROMPT_REQUIRED")
    if type(auto_image_resize) is not bool:
        _fail("Automatic reference resize must be a boolean.", "IMAGE_OPTION_INVALID")
    effective_options = _validated_model_options(model, model_options)
    refs = []
    for reference in references:
        if len(refs) >= model.max_reference_images:
            _fail("Too many reference images for the selected model.", "IMAGE_LIMIT")
        refs.append(reference)
    if (task == "text-to-image" and refs) or (task == "image-to-image" and not refs):
        _fail("Reference images do not match the selected image task.", "INVALID_REFERENCE")
    request_id = _identifier(client_request_id or "img-" + uuid4().hex, "client request ID")
    payload = {"provider": model.provider, "model": model.model_id, "task": task, "prompt": prompt,
               "persistence_scope": "personal_local", "publish_to_reviews": False,
               "ratio": ratio, "image_size": image_size, "output_format": output_format,
               "reference_images": [], "client_request_id": request_id}
    if provider_request_contract:
        payload["provider_request_contract"] = provider_request_contract
    if model.option_schema_revision:
        payload["model_options"] = effective_options
        payload["model_options_schema_revision"] = model.option_schema_revision
    request_limit = min(MAX_REQUEST_BYTES, capabilities.max_request_bytes)
    base_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))
    # Account for data-URI framing and Base64 padding as well as raw bytes.
    reference_budget = min(model.max_reference_bytes, max(0, (request_limit - base_size - len(refs) * 30) // 4 * 3))
    decoded: list[ValidatedImage] = []
    used_bytes = 0
    for value in refs:
        image = _reference_data(value, max_bytes=MAX_IMAGE_BYTES if auto_image_resize else model.max_reference_bytes)
        if provider_request_contract and len(image.data) > model.max_reference_image_bytes:
            if not auto_image_resize:
                _fail("An input image exceeds the native per-image limit. Turn on Auto Image Resize or use a smaller image.",
                    "IMAGE_LIMIT")
            image = _shrink_native_reference(image, model.max_reference_image_bytes)
        used_bytes += len(image.data)
        if used_bytes > (MAX_RESIZE_INPUT_BYTES if auto_image_resize else model.max_reference_bytes):
            _fail("Combined reference images exceed the model byte limit.", "IMAGE_LIMIT")
        decoded.append(image)
    if used_bytes > reference_budget:
        if not auto_image_resize or reference_budget <= 0:
            _fail("Reference images exceed the model or Broker request byte budget.", "IMAGE_LIMIT")
        shrink = _shrink_native_reference if provider_request_contract else _shrink_reference
        decoded = [shrink(image, max(1, reference_budget * len(image.data) // used_bytes)) for image in decoded]
    payload["reference_images"] = ["data:" + image.mime_type + ";base64," + base64.b64encode(image.data).decode("ascii") for image in decoded]
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(serialized.encode("utf-8")) > request_limit:
        _fail("Image request exceeds the Broker request limit.", "IMAGE_LIMIT")
    return ImageInvocation(request_id, model.provider, model.model_id, serialized, admission,
        json.dumps(admission.headers, sort_keys=True) if admission is not None else "{}")


def validate_job(raw: Any, *, expected_job_id: str = "", invocation: ImageInvocation | None = None,
                 client_request_id: str = "", allow_client_lookup: bool = False) -> dict[str, Any]:
    if (not isinstance(raw, dict) or raw.get("schema") != JOB_SCHEMA or type(raw.get("version")) is not int
            or raw["version"] != 1 or raw.get("status") not in JOB_SUCCESS_STATUSES | JOB_FAILURE_STATUSES | JOB_PENDING_STATUSES
            or raw.get("persistence_scope") != "personal_local" or raw.get("publish_to_reviews") is not False):
        _fail("Broker returned an invalid image job record.")
    for key in ("job_id", "provider", "model", "client_request_id"):
        _identifier(raw.get(key), key)
    if expected_job_id and raw["job_id"] != expected_job_id and not (
        allow_client_lookup and expected_job_id == raw["client_request_id"]
    ):
        _fail("Image result belongs to a different Task ID.", "IMAGE_IDENTITY_MISMATCH")
    expected_request = invocation.client_request_id if invocation else client_request_id
    if expected_request and raw["client_request_id"] != expected_request:
        _fail("Image result belongs to a different request.", "IMAGE_IDENTITY_MISMATCH")
    if invocation and any(raw[key] != value for key, value in (
        ("provider", invocation.provider), ("model", invocation.model_id)
    )):
        _fail("Image result belongs to a different model.", "IMAGE_IDENTITY_MISMATCH")
    if invocation and (contract := invocation.payload().get("provider_request_contract")):
        if raw.get("provider_request_contract") != contract:
            _fail("Image result belongs to a different provider contract.", "IMAGE_IDENTITY_MISMATCH")
    if raw["status"] in JOB_SUCCESS_STATUSES:
        results = raw.get("results", [raw.get("result")])
        if (not isinstance(results, list) or not 1 <= len(results) <= 128
                or results[0] != raw.get("result")):
            _fail("Broker returned an invalid ordered image result list.")
        urls = set()
        for result in results:
            if not isinstance(result, dict) or not isinstance(result.get("url"), str) or result.get("mime_type") not in _MIME_FORMATS:
                _fail("Broker did not return a supported image result.")
            if result["url"] in urls:
                _fail("Broker returned duplicate image results.", "IMAGE_IDENTITY_MISMATCH")
            urls.add(result["url"])
            if result.get("sha256") and (not isinstance(result["sha256"], str) or re.fullmatch(r"[a-fA-F0-9]{64}", result["sha256"]) is None):
                _fail("Broker image result checksum is invalid.")
            if "results" in raw and not result.get("sha256"):
                _fail("Ordered image results require individual checksums.")
        text = raw.get("text", "")
        if not isinstance(text, str) or len(text) > 65536:
            _fail("Broker returned invalid image commentary.")
    # Return a detached record: callers cannot mutate a transport-owned cache.
    return json.loads(json.dumps(raw, ensure_ascii=False))


def _check_alive(is_alive: Callable[[], bool] | None) -> None:
    if is_alive is not None and not is_alive():
        _fail("Image generation was cancelled locally; any accepted server Task is preserved.", "IMAGE_CANCELLED")


def save_image_atomic(image: ValidatedImage, output_path: str | Path, *,
                      is_alive: Callable[[], bool] | None = None) -> SavedImage:
    """Publish a complete image without replacing any existing user file."""
    destination = Path(output_path).expanduser()
    if not destination.name or destination.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        destination = destination.with_suffix(_EXTENSIONS[image.mime_type])
    acceptable = {".jpg", ".jpeg"} if image.mime_type == "image/jpeg" else {_EXTENSIONS[image.mime_type]}
    if destination.suffix.lower() not in acceptable:
        destination = destination.with_suffix(_EXTENSIONS[image.mime_type])
    _check_alive(is_alive)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(image.data)
            stream.flush()
            os.fsync(stream.fileno())
        for index in range(10000):
            _check_alive(is_alive)
            candidate = destination if index == 0 else destination.with_name(f"{destination.stem}_v{index + 1:03d}{destination.suffix}")
            try:
                # Hard-link publication is atomic and refuses existing files on
                # NTFS and POSIX; unlike replace(), user media is never replaced.
                os.link(temporary, candidate)
            except FileExistsError:
                continue
            except OSError as exc:
                raise ImageGenerationError("Image could not be published atomically to this folder.", code="IMAGE_SAVE_FAILED") from exc
            return SavedImage(candidate, image.mime_type, image.width, image.height, image.sha256)
        _fail("Image output has too many existing numbered files.", "IMAGE_SAVE_FAILED")
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            # A completed, validated image remains successful even if a
            # filesystem scanner temporarily holds the staging link open.
            pass


def _broker_auth_failure(exc: BaseException) -> bool:
    """Recognize the real Broker authentication type without importing video at module load."""
    if getattr(exc, "status_code", None) == 401:
        return True
    return any(cls.__name__ == "_BrokerAuthenticationError" and cls.__module__ == "HMBSeedanceGeneration"
               for cls in type(exc).__mro__)


_SAFE_IMAGE_JOB_FAILURES = {
    # Server-owned finite codes; never surface raw error text or provider bodies.
    "image_model_not_allowed": "The selected image model is not allowed or enabled on the Broker. Ask the server administrator to check it.",
    "image_credentials_not_ready": "The image provider credential is not ready on the Broker. Ask the server administrator to check it.",
    "image_readiness_changed": "The image model or provider configuration changed while this Task was queued. Ask the server administrator to check it.",
    "image_search_not_ready": "The requested image search capability is not ready on the Broker.",
    "image_reserved_input_invalid": "The Broker could not use the saved image inputs for this Task.",
    "image_storage_unavailable": "The Broker image storage was unavailable for this Task.",
    "image_provider_rejected": "The image provider rejected this Task. Ask the server administrator to check the provider status.",
}


def image_job_failure_message(job: dict[str, Any]) -> str:
    """Return only a fixed message for recognized terminal server codes."""
    error = job.get("error") if isinstance(job, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return _SAFE_IMAGE_JOB_FAILURES.get(code, "") if isinstance(code, str) else ""


class ImageGenerationBroker:
    """Image-specific protocol over the existing user-wide Broker auth session."""
    def __init__(self, bridge: Any = None, *, server_url: str | None = None) -> None:
        if bridge is None:
            from HMBSeedanceGeneration import _HMBAIBrokerBridge
            bridge = _HMBAIBrokerBridge(server_url=server_url)
        self._bridge = bridge
        self.server_url = broker_config.normalize_broker_base_url(bridge.server_url)
        self._capabilities: ImageCapabilities | None = None

    def account_snapshot(self, *, connect: bool = False) -> Any:
        return self._bridge.account_snapshot(connect=connect)

    def capabilities(self, *, timeout: float = 15) -> ImageCapabilities:
        self._capabilities = None
        try:
            admission = queue.discover(self._bridge, timeout=timeout)
            if admission is not None:
                queue.require_bound(self._bridge, admission, "image")
            raw = admission.profile("image_syntax") if admission is not None else self._bridge._request_json("GET", "/api/v1/image-generation/capabilities", payload=None, timeout=timeout)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if _broker_auth_failure(exc):
                raise ImageGenerationError("Broker login is required before checking image models. Connect again; no image was submitted.",
                    code="IMAGE_BROKER_LOGIN_REQUIRED") from exc
            if status in {404, 405, 501}:
                raise ImageGenerationError(
                    "This Broker image adapter is not installed yet. No image was submitted.",
                    code="IMAGE_GENERATION_UNSUPPORTED") from exc
            raise ImageGenerationError("The Broker image model catalogue is temporarily unavailable. No image was submitted.",
                code="IMAGE_BROKER_UNAVAILABLE") from exc
        result = replace(parse_capabilities(raw), _queue_admission=admission)
        self._capabilities = result
        return result

    def create(self, invocation: ImageInvocation, *, on_submission_prepared: Callable[[ImageInvocation], None] | None = None,
               is_alive: Callable[[], bool] | None = None, timeout: float = 300) -> dict[str, Any]:
        _check_alive(is_alive)
        caps = self._capabilities
        if caps is None:
            _fail("Refresh the image model catalogue before rendering.", "IMAGE_GENERATION_UNAVAILABLE")
        queue_kwargs = {}
        if invocation._queue_admission is not caps._queue_admission:
            _fail("Image queue admission changed after preparation.", "IMAGE_IDENTITY_MISMATCH")
        if caps._queue_admission is not None:
            queue.require_bound(self._bridge, caps._queue_admission, "image")
            queue_kwargs = {"queue_admission": caps._queue_admission, "queue_operation": "image"}
        payload = invocation.payload()
        # Revalidate the immutable snapshot against this exact transport's
        # catalogue before crossing the billable boundary.
        checked = prepare_invocation(caps, model_id=invocation.model_id, provider=invocation.provider,
            task=payload["task"], prompt=payload["prompt"],
            ratio=payload["ratio"], image_size=payload["image_size"], output_format=payload["output_format"],
            references=payload["reference_images"], client_request_id=invocation.client_request_id,
            model_options=payload.get("model_options"),
            provider_request_contract=payload.get("provider_request_contract", ""))
        if checked != invocation:
            _fail("Image invocation no longer matches its prepared snapshot.", "IMAGE_IDENTITY_MISMATCH")
        if on_submission_prepared is not None:
            on_submission_prepared(invocation)
        _check_alive(is_alive)
        try:
            raw = self._bridge._request_json("POST", "/api/v1/generate/image", payload=payload,
                timeout=timeout, submission=True, idempotency_key=invocation.client_request_id, **queue_kwargs)
            return validate_job(raw, invocation=invocation)
        except Exception as exc:
            # No retry: even invalid accepted JSON can represent a charged Task.
            if isinstance(exc, ImageGenerationError):
                exc.submission_outcome_unknown = True
                raise
            unknown = bool(getattr(exc, "submission_outcome_unknown", not isinstance(getattr(exc, "status_code", None), int)))
            raise ImageGenerationError(
                "The Broker image submission was not confirmed. Retrieve the saved request ID before submitting another image."
                if unknown else "The Broker rejected the image submission; no new image request was confirmed.",
                code="IMAGE_SUBMISSION_UNKNOWN" if unknown else "IMAGE_SUBMISSION_REJECTED",
                submission_outcome_unknown=unknown) from exc

    def refresh(self, job_id: str, *, client_request_id: str = "", invocation: ImageInvocation | None = None,
                timeout: float = 300) -> dict[str, Any]:
        job_id = _identifier(job_id, "Task ID")
        lookup = bool(self._capabilities and self._capabilities.client_request_lookup)
        if client_request_id and job_id == client_request_id and not lookup:
            _fail("This Broker has not advertised recovery by client request ID. Keep this ID for server recovery.", "IMAGE_RECOVERY_UNSUPPORTED")
        try:
            raw = self._bridge._request_json("POST", "/api/v1/jobs/" + quote(job_id, safe="") + "/refresh",
                                             payload=None, timeout=timeout)
        except Exception as exc:
            if _broker_auth_failure(exc):
                raise ImageGenerationError(
                    f"Broker login is unavailable or expired. Connect again and retrieve the same Task {job_id}; no replacement image was submitted.",
                    code="IMAGE_BROKER_LOGIN_REQUIRED") from exc
            raise ImageGenerationError(
                f"The Broker could not check image Task {job_id}. Retrieve the same Task again; no replacement image was submitted.",
                code="IMAGE_STATUS_UNAVAILABLE") from exc
        return validate_job(raw, expected_job_id=job_id, invocation=invocation,
                            client_request_id=client_request_id, allow_client_lookup=lookup)

    def save_result(self, job: dict[str, Any], output_path: str | Path, *,
                    is_alive: Callable[[], bool] | None = None, result_index: int = 0) -> SavedImage:
        job = validate_job(job)
        if job["status"] not in JOB_SUCCESS_STATUSES:
            _fail("Image Task has not completed successfully.", "IMAGE_RESULT_NOT_READY")
        _check_alive(is_alive)
        results = job.get("results", [job["result"]])
        if type(result_index) is not int or not 0 <= result_index < len(results):
            _fail("Select an image belonging to this completed Task.", "IMAGE_IDENTITY_MISMATCH")
        result = results[result_index]
        url = result["url"]
        if re.fullmatch(re.escape(self.server_url) + r"/api/assets/[A-Za-z0-9_-]{43}", url) is None:
            _fail("Broker authorization was refused for an external or invalid image URL.", "IMAGE_RESULT_UNTRUSTED")
        request = urllib.request.Request(url, headers={"Accept": result["mime_type"],
            "Authorization": "Bearer " + self._bridge._load_access_token()}, method="GET")
        try:
            with self._bridge._opener.open(request, timeout=300) as response:
                if not callable(getattr(response, "geturl", None)) or response.geturl() != url:
                    _fail("Broker image response changed its origin or path.", "IMAGE_RESULT_UNTRUSTED")
                raw = response.read(MAX_IMAGE_BYTES + 1)
        except ImageGenerationError:
            raise
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise ImageGenerationError("Broker image download failed. Retrieve this Task again.", code="IMAGE_DOWNLOAD_FAILED") from exc
        image = validate_image_bytes(raw, advertised_mime=result["mime_type"], advertised_sha256=result.get("sha256", ""))
        _check_alive(is_alive)
        return save_image_atomic(image, output_path, is_alive=is_alive)
