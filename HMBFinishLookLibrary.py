from __future__ import annotations

import copy
import hashlib
import hmac
import importlib.util
import json
import logging
import math
import re
import sys
import threading
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence


_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


def _load_hmb_common() -> Any:
    module_path = _THIS_DIR / "_hmb_common.py"
    module_name = "_hmb_gp_production_common"
    existing = sys.modules.get(module_name)
    if existing is not None and Path(getattr(existing, "__file__", "")).resolve() == module_path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load HMB common module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_hmb = _load_hmb_common()
DataNode = _hmb.DataNode
Parameter = _hmb.Parameter
ParameterMode = _hmb.ParameterMode
add_group = _hmb.add_group
set_output = _hmb.set_output
parameter_exists = _hmb.parameter_exists

try:
    from griptape_nodes.traits.widget import Widget  # type: ignore
except Exception:
    Widget = None  # type: ignore


LOGGER = logging.getLogger("griptape_nodes")
EPSILON = 1e-6
SCHEMA_VERSION = 1
WIDGET_NAME = "HMBFinishLookLibraryWidget"
WIDGET_LIBRARY_NAME = "HMB_GP_Production"
WIDGET_PARAMETER_NAME = "HMB_FINISH_LOOK_UI_STATE"
REMOTE_INPUT_PARAMETER_NAME = "FINISH_LOOK_REMOTE_IN"

FINISH_LOOK_OUTPUT_PARAMETER_NAME = "FINISH_LOOK_OUT"
SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME = "SHOT_FINISH_LOOK_OUT"
FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME = "HMB_FINISH_LOOK_STATE"
REMOTE_STATUS_OUTPUT_PARAMETER_NAME = "HMB_FINISH_LOOK_REMOTE_STATUS"

REMOTE_SCHEMA = "hmb-finish-look-remote-patch"
MAX_REQUEST_ID_LENGTH = 128
MAX_REMOTE_HISTORY = 256
SHOT_ROUTING_CATALOG_SCHEMA = "hmb-shot-routing-catalog"
SHOT_ROUTING_CATALOG_VERSION = 1
SHOT_SUBSCRIPTION_SCHEMA = "hmb-shot-channel-subscription"
SHOT_SUBSCRIPTION_VERSION = 1
FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA = "hmb-finish-look-shot-snapshot"
FINISH_LOOK_SHOT_SNAPSHOT_VERSION = 1
MAX_SHOTS = 5
FINISH_LOOK_NODE_WIDTH = 980
FINISH_LOOK_NODE_HEIGHT = 1040
FINISH_LOOK_NODE_MIN_WIDTH = 700
FINISH_LOOK_NODE_MIN_HEIGHT = 620
FINISH_LOOK_WIDGET_HEIGHT = 940
FINISH_LOOK_WIDGET_MIN_HEIGHT = 720


class FinishLookValidationError(ValueError):
    """A state or remote request violates the public Finish Look contract."""


class FilmStock(NamedTuple):
    name: str
    kind: str
    ignores_negative: bool = False


FILM_STOCK_CATALOG: tuple[FilmStock, ...] = (
    FilmStock("None", "negative"),
    FilmStock("Kodak 5245", "negative"),
    FilmStock("Kodak 5246", "negative"),
    FilmStock("Kodak 5248", "negative"),
    FilmStock("Kodak 5274", "negative"),
    FilmStock("Kodak 5277", "negative"),
    FilmStock("Kodak 5279", "negative"),
    FilmStock("Kodak 5284", "negative"),
    FilmStock("Kodak 5289", "negative"),
    FilmStock("Kodak 5293", "negative"),
    FilmStock("Kodak 5298", "negative"),
    FilmStock("K SFX200T", "negative"),
    FilmStock("Kodak 5217", "negative"),
    FilmStock("Kodak 5218", "negative"),
    FilmStock("None", "print"),
    FilmStock("Kodak 2383", "print"),
    FilmStock("Kodak 2393", "print"),
    FilmStock("Kodak 2395", "print"),
    FilmStock("Kodak 5386", "print"),
    FilmStock("Kodak 5285 Rev", "reversal", True),
    FilmStock("Kodak 7270 Rev", "reversal", True),
)
NEGATIVE_FILM_STOCKS: tuple[str, ...] = tuple(
    stock.name for stock in FILM_STOCK_CATALOG if stock.kind == "negative"
)
PRINT_FILM_STOCKS: tuple[str, ...] = tuple(
    stock.name for stock in FILM_STOCK_CATALOG if stock.kind in {"print", "reversal"}
)
REVERSAL_FILM_STOCKS: frozenset[str] = frozenset(
    stock.name for stock in FILM_STOCK_CATALOG if stock.ignores_negative
)

DEFAULT_FINISH_LOOK_STATE: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "beauty": {
        "enabled": True,
        "soften_shadows": 0.11,
        "shadow_threshold": 0.27,
        "saturation": 1.0,
        "brightness": 1.0,
        "glow_brightness": 0.0,
        "glow_threshold": 0.2,
        "glow_width": 16.0,
        "soft_focus": 0.0,
        "blur_amount": 0.0,
        "pore_size": 0.0,
        "reduce_shine": 0.0,
    },
    "film": {
        "enabled": True,
        "negative_film": "Kodak 5245",
        "print_film": "Kodak 2383",
        "scale_cc": 0.3,
        "printer_light_r": 26,
        "printer_light_g": 25,
        "printer_light_b": 24,
        "input_gamma": 1.2,
        "output_gamma": 2.2,
        "negative_exposure": 0.0,
        "print_exposure": 0.0,
        "glow_brightness": 0.1,
        "soft_focus": 0.0,
        "vignette": 0.0,
    },
}

DEFAULT_REMOTE_STATUS: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "status": "idle",
    "code": "idle",
    "message": "",
    "request_id": "",
    "revision": 0,
}

def default_finish_look_state() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_FINISH_LOOK_STATE)


def film_stock_catalog_payload() -> dict[str, list[str]]:
    return {
        "negative": list(NEGATIVE_FILM_STOCKS),
        "print": list(PRINT_FILM_STOCKS),
        "reversal": sorted(REVERSAL_FILM_STOCKS),
    }


def _shot_only() -> dict[str, Any]:
    return {
        "channel_uuid": "",
        "shot_uuid": "",
        "number": 1,
        "name": "Only",
    }


def _normalize_shot_catalog(
    value: Any,
    *,
    strict: bool = False,
    allow_sparse: bool = False,
) -> dict[str, Any]:
    """Normalize the compact ImageAsset-owned Shot catalog.

    Finish Look never persists media in its selector state.  The catalog is
    only a bounded UUID/name option list supplied by the same-flow router.
    """

    if not value:
        return {}
    if not isinstance(value, Mapping):
        if strict:
            raise FinishLookValidationError("Shot catalog must be an object.")
        return {}
    required = {
        "schema",
        "version",
        "publisher_instance_uuid",
        "channel_uuid",
        "generation",
        "metadata_sha256",
        "shots",
    }
    if set(value) != required:
        if strict:
            raise FinishLookValidationError("Shot catalog shape is invalid.")
        return {}
    publisher = str(value.get("publisher_instance_uuid") or "")
    channel = str(value.get("channel_uuid") or "")
    metadata_sha256 = str(value.get("metadata_sha256") or "").casefold()
    generation = value.get("generation")
    shots_value = value.get("shots")
    if (
        value.get("schema") != SHOT_ROUTING_CATALOG_SCHEMA
        or value.get("version") != SHOT_ROUTING_CATALOG_VERSION
        or not publisher
        or publisher != publisher.strip()
        or len(publisher) > 128
        or not channel
        or channel != channel.strip()
        or len(channel) > 128
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or not 1 <= generation <= (1 << 53) - 1
        or re.fullmatch(r"[0-9a-f]{64}", metadata_sha256) is None
        or not isinstance(shots_value, list)
        or not 1 <= len(shots_value) <= MAX_SHOTS
    ):
        if strict:
            raise FinishLookValidationError("Shot catalog metadata is invalid.")
        return {}
    shots: list[dict[str, Any]] = []
    shot_ids: set[str] = set()
    shot_numbers: set[int] = set()
    for raw in shots_value:
        if not isinstance(raw, Mapping) or set(raw) != {
            "shot_uuid",
            "number",
            "name",
            "revision",
        }:
            if strict:
                raise FinishLookValidationError("Shot catalog row is invalid.")
            return {}
        shot_uuid = str(raw.get("shot_uuid") or "")
        name = " ".join(str(raw.get("name") or "").split())
        number = raw.get("number")
        revision = raw.get("revision")
        if (
            not shot_uuid
            or shot_uuid != shot_uuid.strip()
            or len(shot_uuid) > 128
            or shot_uuid in shot_ids
            or isinstance(number, bool)
            or not isinstance(number, int)
            or not 1 <= number <= MAX_SHOTS
            or number in shot_numbers
            or not name
            or len(name) > 128
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or not 0 <= revision <= (1 << 53) - 1
        ):
            if strict:
                raise FinishLookValidationError("Shot catalog row value is invalid.")
            return {}
        shot_ids.add(shot_uuid)
        shot_numbers.add(number)
        shots.append(
            {
                "shot_uuid": shot_uuid,
                "number": number,
                "name": name,
                "revision": revision,
            }
        )
    shots.sort(key=lambda item: (item["number"], item["shot_uuid"]))
    if (
        not allow_sparse
        and [item["number"] for item in shots] != list(range(1, len(shots) + 1))
    ):
        if strict:
            raise FinishLookValidationError("Shot catalog numbering is invalid.")
        return {}
    document = {
        "channel_uuid": channel,
        "generation": generation,
        "shots": shots,
    }
    expected_sha256 = hashlib.sha256(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if not hmac.compare_digest(metadata_sha256, expected_sha256):
        if strict:
            raise FinishLookValidationError("Shot catalog hash does not match.")
        return {}
    return {
        "schema": SHOT_ROUTING_CATALOG_SCHEMA,
        "version": SHOT_ROUTING_CATALOG_VERSION,
        "publisher_instance_uuid": publisher,
        "channel_uuid": channel,
        "generation": generation,
        "metadata_sha256": metadata_sha256,
        "shots": shots,
    }


def _normalize_shot_selection(value: Any, catalog: Any = None) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    channel = str(source.get("channel_uuid") or "").strip()[:128]
    shot_uuid = str(source.get("shot_uuid") or "").strip()[:128]
    if not channel or not shot_uuid:
        return _shot_only()
    normalized_catalog = _normalize_shot_catalog(catalog, allow_sparse=True)
    if normalized_catalog and normalized_catalog.get("channel_uuid") != channel:
        return _shot_only()
    selected = next(
        (
            item
            for item in normalized_catalog.get("shots", [])
            if item.get("shot_uuid") == shot_uuid
        ),
        None,
    )
    if normalized_catalog and selected is None:
        return _shot_only()
    try:
        number = max(1, min(MAX_SHOTS, int(source.get("number") or 1)))
    except (TypeError, ValueError, OverflowError):
        number = 1
    if selected is not None:
        number = int(selected["number"])
        name = str(selected["name"])
    else:
        name = " ".join(str(source.get("name") or f"Shot {number}").split())[:128]
    return {
        "channel_uuid": channel,
        "shot_uuid": shot_uuid,
        "number": number,
        "name": name or f"Shot {number}",
    }


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise FinishLookValidationError(f"{field} must contain valid JSON.") from exc
    if not isinstance(value, Mapping):
        raise FinishLookValidationError(f"{field} must be an object.")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise FinishLookValidationError(f"{field} is missing: {', '.join(missing)}.")
    if unknown:
        raise FinishLookValidationError(f"{field} contains unsupported keys: {', '.join(unknown)}.")


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise FinishLookValidationError(f"{field} must be boolean.")
    return value


def _number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FinishLookValidationError(f"{field} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise FinishLookValidationError(f"{field} must be finite.")
    if minimum is not None and result < minimum:
        raise FinishLookValidationError(f"{field} must be at least {format_number(minimum)}.")
    if maximum is not None and result > maximum:
        raise FinishLookValidationError(f"{field} must be at most {format_number(maximum)}.")
    return result


def _integer(
    value: Any,
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    result = _number(value, field, minimum=minimum, maximum=maximum)
    if not result.is_integer():
        raise FinishLookValidationError(f"{field} must be an integer.")
    return int(result)


def _choice(value: Any, choices: Sequence[str], field: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise FinishLookValidationError(f"{field} must be one of: {', '.join(choices)}.")
    return value


def validate_finish_look_state(value: Any) -> dict[str, Any]:
    state = _mapping(value, "Finish Look state")
    _exact_keys(state, {"schema_version", "beauty", "film"}, "Finish Look state")
    if type(state.get("schema_version")) is not int or state["schema_version"] != SCHEMA_VERSION:
        raise FinishLookValidationError("schema_version must be integer 1.")

    beauty = _mapping(state["beauty"], "beauty")
    beauty_keys = {
        "enabled",
        "soften_shadows",
        "shadow_threshold",
        "saturation",
        "brightness",
        "glow_brightness",
        "glow_threshold",
        "glow_width",
        "soft_focus",
        "blur_amount",
        "pore_size",
        "reduce_shine",
    }
    _exact_keys(beauty, beauty_keys, "beauty")
    normalized_beauty = {
        "enabled": _boolean(beauty["enabled"], "beauty.enabled"),
        "soften_shadows": _number(beauty["soften_shadows"], "beauty.soften_shadows", minimum=-1, maximum=1),
        "shadow_threshold": _number(beauty["shadow_threshold"], "beauty.shadow_threshold", minimum=0, maximum=1),
        "saturation": _number(beauty["saturation"], "beauty.saturation", minimum=-2, maximum=8),
        "brightness": _number(beauty["brightness"], "beauty.brightness", minimum=0),
        "glow_brightness": _number(beauty["glow_brightness"], "beauty.glow_brightness", minimum=0),
        "glow_threshold": _number(beauty["glow_threshold"], "beauty.glow_threshold", minimum=0),
        "glow_width": _number(beauty["glow_width"], "beauty.glow_width", minimum=0),
        "soft_focus": _number(beauty["soft_focus"], "beauty.soft_focus", minimum=0),
        "blur_amount": _number(beauty["blur_amount"], "beauty.blur_amount", minimum=0),
        "pore_size": _number(beauty["pore_size"], "beauty.pore_size", minimum=0),
        "reduce_shine": _number(beauty["reduce_shine"], "beauty.reduce_shine", minimum=0, maximum=1),
    }

    film = _mapping(state["film"], "film")
    film_keys = {
        "enabled",
        "negative_film",
        "print_film",
        "scale_cc",
        "printer_light_r",
        "printer_light_g",
        "printer_light_b",
        "input_gamma",
        "output_gamma",
        "negative_exposure",
        "print_exposure",
        "glow_brightness",
        "soft_focus",
        "vignette",
    }
    _exact_keys(film, film_keys, "film")
    normalized_film = {
        "enabled": _boolean(film["enabled"], "film.enabled"),
        "negative_film": _choice(film["negative_film"], NEGATIVE_FILM_STOCKS, "film.negative_film"),
        "print_film": _choice(film["print_film"], PRINT_FILM_STOCKS, "film.print_film"),
        "scale_cc": _number(film["scale_cc"], "film.scale_cc", minimum=0, maximum=5),
        "printer_light_r": _integer(film["printer_light_r"], "film.printer_light_r", minimum=0, maximum=50),
        "printer_light_g": _integer(film["printer_light_g"], "film.printer_light_g", minimum=0, maximum=50),
        "printer_light_b": _integer(film["printer_light_b"], "film.printer_light_b", minimum=0, maximum=50),
        "input_gamma": _number(film["input_gamma"], "film.input_gamma", minimum=0.1),
        "output_gamma": _number(film["output_gamma"], "film.output_gamma", minimum=0.1),
        "negative_exposure": _number(film["negative_exposure"], "film.negative_exposure"),
        "print_exposure": _number(film["print_exposure"], "film.print_exposure"),
        "glow_brightness": _number(film["glow_brightness"], "film.glow_brightness", minimum=0),
        "soft_focus": _number(film["soft_focus"], "film.soft_focus", minimum=0, maximum=1),
        "vignette": _number(film["vignette"], "film.vignette", minimum=0, maximum=1),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "beauty": normalized_beauty,
        "film": normalized_film,
    }


parse_finish_look_state = validate_finish_look_state


def format_number(value: float) -> str:
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def is_zero(value: float) -> bool:
    return abs(float(value)) <= EPSILON


def join_sentences(parts: Sequence[str]) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _common_strength(value: float) -> str:
    magnitude = abs(float(value))
    if magnitude <= EPSILON:
        return ""
    if magnitude <= 0.05:
        return "nearly imperceptible"
    if magnitude <= 0.12:
        return "very subtle"
    if magnitude <= 0.25:
        return "subtle"
    if magnitude <= 0.5:
        return "moderate"
    return "pronounced"


def _beauty_shadow_phrase(value: float) -> str:
    if value <= -0.21:
        return "pronounced shadow enhancement"
    if value <= -0.06:
        return "moderately strengthened shadow definition"
    if value <= 0.05:
        return "no meaningful shadow softening"
    if value <= 0.12:
        return "gently softened shadow transitions"
    if value <= 0.25:
        return "moderately softened shadow transitions"
    return "pronounced shadow softening"


def _beauty_threshold_phrase(value: float) -> str:
    if value <= 0.14:
        return "at a low shadow threshold"
    if value <= 0.39:
        return "at a moderate threshold"
    return "across a broad shadow range"


def _beauty_saturation_clause(value: float) -> str:
    if value <= -1.01:
        return "Use a strongly amplified inverted-chroma response on character surfaces"
    if value <= -0.51:
        return "Use a clear inverted-chroma response on character surfaces"
    if value < -EPSILON:
        return "Use a restrained inverted-chroma response on character surfaces"
    if abs(value) <= EPSILON:
        return "Use a monochrome character-surface color response"
    if value <= 0.89:
        return "Use visibly reduced character-surface saturation"
    if value <= 0.97:
        return "Use slightly reduced character-surface saturation"
    if value <= 1.02:
        return "Keep character-surface saturation neutral at full strength"
    if value <= 1.10:
        return "Use subtly increased character-surface saturation"
    return "Use increased character-surface saturation"


def _beauty_brightness_clause(value: float) -> str:
    if 0.98 <= value <= 1.02:
        return "maintain neutral character-surface brightness"
    direction = "reduce" if value < 0.98 else "increase"
    return f"{direction} character-surface brightness to value {format_number(value)}"


def compile_beauty_glow_prompt(beauty: Mapping[str, Any]) -> str:
    value = float(beauty["glow_brightness"])
    if value <= EPSILON:
        return ""
    threshold = float(beauty["glow_threshold"])
    threshold_clause = (
        "across all non-black character face, skin, and material regions"
        if threshold <= EPSILON
        else (
            "only in character face, skin, and material regions brighter than threshold "
            f"{format_number(threshold)}"
        )
    )
    return (
        f"Add a {_common_strength(value)} character beauty glow {threshold_clause}, "
        f"with a configured glow width of {format_number(float(beauty['glow_width']))}."
    )


def compile_beauty_prompt(state: Mapping[str, Any]) -> str:
    beauty = state.get("beauty") if isinstance(state.get("beauty"), Mapping) else state
    if not bool(beauty.get("enabled", True)):
        return ""
    parts = [
        (
            "Apply Character Beauty exclusively inside each visible character's matte and silhouette, "
            "including only character-owned face, eyes, teeth, skin when present, hair, clothing, "
            "accessories, and intrinsic material surfaces. Treat every character matte as a hard "
            "processing boundary."
        ),
        (
            "Exclude the background and environment completely, including sets, terrain, architecture, "
            "vegetation, sky, atmosphere, and environment-only objects; Character Beauty must not alter "
            "their pixels, lighting, color, contrast, detail, or material response."
        ),
        (
            "Within that character-only scope, apply restrained beauty processing with "
            f"{_beauty_shadow_phrase(float(beauty['soften_shadows']))} "
            f"{_beauty_threshold_phrase(float(beauty['shadow_threshold']))}, while preserving "
            "clean character edges, material definition, and natural character-surface texture."
        ),
        (
            f"{_beauty_saturation_clause(float(beauty['saturation']))} and "
            f"{_beauty_brightness_clause(float(beauty['brightness']))}."
        ),
        compile_beauty_glow_prompt(beauty),
    ]
    advanced = (
        ("soft_focus", "character-surface soft-focus diffusion"),
        ("blur_amount", "edge-aware character-surface blur"),
    )
    for key, label in advanced:
        value = float(beauty[key])
        if value > EPSILON:
            parts.append(
                f"Apply {_common_strength(value)} {label} at value {format_number(value)}."
            )
    pore_size = float(beauty["pore_size"])
    if pore_size > EPSILON:
        parts.append(
            "Preserve character texture features smaller than the pore-size threshold "
            f"{format_number(pore_size)}."
        )
    reduce_shine = float(beauty["reduce_shine"])
    if reduce_shine > EPSILON:
        parts.append(
            f"Apply {_common_strength(reduce_shine)} reduction of bright character-surface shine at value "
            f"{format_number(reduce_shine)} while preserving local color."
        )
    if all(float(beauty[key]) <= EPSILON for key in ("soft_focus", "blur_amount", "pore_size", "reduce_shine")):
        parts.append(
            "Do not add character soft-focus diffusion, skin blur, pore removal, shine reduction, "
            "or any airbrushed or plasticky character smoothing."
        )
    parts.append(
        "Preserve a clean, natural, polished character appearance with stable color fidelity and intact "
        "local detail. Every Character Beauty control in this block is character-only and must not spill, "
        "feather, or propagate beyond the character matte into the background or environment."
    )
    return "CHARACTER BEAUTY — CHARACTER-MATTE-ONLY SCOPE\n" + join_sentences(parts)


def _is_reversal(print_film: str) -> bool:
    return print_film in REVERSAL_FILM_STOCKS


def _film_stock_clause(film: Mapping[str, Any]) -> str:
    negative = str(film["negative_film"])
    print_film = str(film["print_film"])
    if _is_reversal(print_film):
        return f"a clean {print_film} reversal-film response"
    if negative != "None" and print_film != "None":
        return (
            f"a clean {negative} negative-film response combined with "
            f"a {print_film} print-film response"
        )
    if negative != "None":
        return f"a clean {negative} negative-film response without an additional print-film stock response"
    if print_film != "None":
        return f"a clean {print_film} print-film response"
    return ""


def compile_film_stock_prompt(film: Mapping[str, Any]) -> str:
    clause = _film_stock_clause(film)
    return f"Apply {clause}." if clause else ""


def _scale_cc_clause(value: float) -> str:
    if value <= EPSILON:
        return ""
    if value <= 0.15:
        return "extremely restrained film color correction"
    if value <= 0.35:
        return "restrained film color correction at low strength"
    if value <= 0.60:
        return "moderate film color correction"
    if value <= 0.85:
        return "strong film color correction"
    return "high-strength film color correction"


def compile_scale_cc_prompt(film: Mapping[str, Any]) -> str:
    clause = _scale_cc_clause(float(film["scale_cc"]))
    return f"Use {clause}." if clause else ""


def _printer_strength(value: float) -> str:
    magnitude = abs(float(value))
    if magnitude <= EPSILON:
        return "neutral"
    if magnitude <= 1:
        return "very subtle"
    if magnitude <= 2:
        return "subtle"
    if magnitude <= 4:
        return "moderate"
    return "strong"


def analyze_printer_lights(r: float, g: float, b: float) -> dict[str, Any]:
    values = tuple(_number(value, f"printer light {name}", minimum=0, maximum=50) for name, value in zip("RGB", (r, g, b)))
    dr, dg, db = (value - 25.0 for value in values)
    common = (dr + dg + db) / 3.0
    relative = {"R": dr - common, "G": dg - common, "B": db - common}
    color_for = {
        ("R", 1): "cyan",
        ("R", -1): "red",
        ("G", 1): "magenta",
        ("G", -1): "green",
        ("B", 1): "yellow",
        ("B", -1): "blue",
    }
    order = {"R": 0, "G": 1, "B": 2}
    selected = sorted(
        ((channel, delta) for channel, delta in relative.items() if abs(delta) > EPSILON),
        key=lambda item: (-abs(item[1]), order[item[0]]),
    )[:2]
    colors = [color_for[(channel, 1 if delta > 0 else -1)] for channel, delta in selected]
    temperature = ""
    if colors and all(color in {"cyan", "blue"} for color in colors):
        temperature = "cool"
    elif colors and all(color in {"red", "yellow"} for color in colors):
        temperature = "warm"
    return {
        "common_density": common,
        "red_channel_delta": relative["R"],
        "green_channel_delta": relative["G"],
        "blue_channel_delta": relative["B"],
        "density_direction": "darker" if common > EPSILON else "lighter" if common < -EPSILON else "neutral",
        "density_strength": _printer_strength(common),
        "colors": colors,
        "temperature": temperature,
        "color_strength": _printer_strength(max((abs(delta) for _, delta in selected), default=0.0)),
    }


def _printer_lights_clause(film: Mapping[str, Any]) -> str:
    analysis = analyze_printer_lights(
        float(film["printer_light_r"]),
        float(film["printer_light_g"]),
        float(film["printer_light_b"]),
    )
    common = float(analysis["common_density"])
    colors = list(analysis["colors"])
    if abs(common) <= EPSILON and not colors:
        return "a neutral printer-light balance"

    density = ""
    if abs(common) > EPSILON:
        density = (
            f"a {analysis['density_strength']} {analysis['density_direction']} "
            "printer-light density"
        )
    color = ""
    if colors:
        temperature = f" {analysis['temperature']}" if analysis["temperature"] else ""
        color = (
            f"a {analysis['color_strength']}{temperature} printer-light bias leaning toward "
            + "-".join(colors)
        )
    if density and color:
        return f"{density}, followed by {color}"
    if density:
        return f"{density} with no color bias"
    return color


def compile_printer_lights_prompt(film: Mapping[str, Any]) -> str:
    return f"Use {_printer_lights_clause(film)}."


def compile_gamma_prompt(film: Mapping[str, Any]) -> str:
    return (
        "Maintain a gently controlled input tonal response corresponding to gamma "
        f"{format_number(float(film['input_gamma']))} and a clean output gamma response around "
        f"{format_number(float(film['output_gamma']))}."
    )


def _exposure_strength(value: float) -> str:
    magnitude = abs(float(value))
    if magnitude <= EPSILON:
        return ""
    if magnitude <= 0.15:
        return "very slight"
    if magnitude <= 0.35:
        return "slight"
    if magnitude <= 0.75:
        return "moderate"
    if magnitude <= 1.5:
        return "strong"
    return "pronounced"


def compile_exposure_prompt(film: Mapping[str, Any]) -> str:
    parts: list[str] = []
    negative = float(film["negative_exposure"])
    if abs(negative) > EPSILON:
        result = "brighter" if negative > 0 else "darker"
        parts.append(
            f"Apply a {_exposure_strength(negative)} negative exposure adjustment of "
            f"{format_number(negative)} stops for a {result} negative response."
        )
    print_value = float(film["print_exposure"])
    if abs(print_value) > EPSILON:
        result = "darker" if print_value > 0 else "lighter"
        parts.append(
            f"Apply a {_exposure_strength(print_value)} print exposure adjustment of "
            f"{format_number(print_value)} stops for a {result} print response."
        )
    return join_sentences(parts)


def compile_film_glow_prompt(film: Mapping[str, Any]) -> str:
    value = float(film["glow_brightness"])
    if value <= EPSILON:
        return ""
    if value <= 0.05:
        return "Add only a nearly imperceptible highlight glow."
    if value <= 0.12:
        return "Add only a very subtle, nearly imperceptible highlight glow."
    if value <= 0.25:
        return "Add a subtle highlight glow."
    if value <= 0.40:
        return "Add a moderate highlight glow."
    return "Add a pronounced highlight glow."


def compile_film_soft_focus_prompt(film: Mapping[str, Any]) -> str:
    value = float(film["soft_focus"])
    if value <= EPSILON:
        return ""
    return (
        f"Mix in a {_common_strength(value)} soft-focus response at value {format_number(value)} "
        "without increasing overall brightness."
    )


def compile_vignette_prompt(film: Mapping[str, Any]) -> str:
    value = float(film["vignette"])
    if value <= EPSILON:
        return ""
    return f"Apply a {_common_strength(value)} corner vignette at value {format_number(value)}."


def compile_film_prompt(film: Mapping[str, Any], *, follows_beauty: bool = False) -> str:
    if not bool(film.get("enabled", True)):
        return ""
    parts: list[str] = [
        (
            "Apply Filter Application across the complete already-resolved final frame as one post-process, "
            "including all characters, the complete background and environment, and resolved FX."
        ),
        (
            "This full-frame filter may change only the final image response. Do not add, remove, replace, "
            "relayout, or regenerate scene content, and do not change character identity or design, geometry, "
            "camera or framing, animation or timing, FX placement, or the established lighting direction."
        ),
    ]
    color_enabled = (
        float(film["scale_cc"]) > EPSILON
        and not (film["negative_film"] == "None" and film["print_film"] == "None")
    )
    if color_enabled:
        stock = _film_stock_clause(film)
        first = f"{'Then apply' if follows_beauty else 'Apply'} {stock}"
        scale = _scale_cc_clause(float(film["scale_cc"]))
        printer = _printer_lights_clause(film)
        if scale:
            first += f", using {scale}"
        if printer:
            first += f" and {printer}"
        parts.append(first + ".")
        parts.append(compile_gamma_prompt(film))
        parts.append(compile_exposure_prompt(film))
    parts.extend(
        [
            compile_film_glow_prompt(film),
            compile_film_soft_focus_prompt(film),
            compile_vignette_prompt(film),
            "Preserve clean local colors, controlled highlights, rich but readable shadows, and stable color separation.",
            "Do not introduce or simulate any film grain.",
        ]
    )
    return "FILTER APPLICATION — FULL-FRAME SCOPE\n" + join_sentences(parts)


def compile_finish_look_prompt(state: Mapping[str, Any]) -> str:
    normalized = validate_finish_look_state(state)
    beauty = compile_beauty_prompt(normalized["beauty"]) if normalized["beauty"]["enabled"] else ""
    film = compile_film_prompt(normalized["film"], follows_beauty=bool(beauty)) if normalized["film"]["enabled"] else ""
    return "\n\n".join(section for section in (beauty, film) if section)


EXPECTED_DEFAULT_FINISH_LOOK_OUT = (
    "CHARACTER BEAUTY — CHARACTER-MATTE-ONLY SCOPE\n"
    "Apply Character Beauty exclusively inside each visible character's matte and silhouette, including only "
    "character-owned face, eyes, teeth, skin when present, hair, clothing, accessories, and intrinsic material "
    "surfaces. Treat every character matte as a hard processing boundary. Exclude the background and environment "
    "completely, including sets, terrain, architecture, vegetation, sky, atmosphere, and environment-only objects; "
    "Character Beauty must not alter their pixels, lighting, color, contrast, detail, or material response. Within "
    "that character-only scope, apply restrained beauty processing with gently softened shadow transitions at a "
    "moderate threshold, while preserving clean character edges, material definition, and natural character-surface "
    "texture. Keep character-surface saturation neutral at full strength and maintain neutral character-surface "
    "brightness. Do not add character soft-focus diffusion, skin blur, pore removal, shine reduction, or any "
    "airbrushed or plasticky character smoothing. Preserve a clean, natural, polished character appearance with "
    "stable color fidelity and intact local detail. Every Character Beauty control in this block is character-only "
    "and must not spill, feather, or propagate beyond the character matte into the background or environment.\n\n"
    "FILTER APPLICATION — FULL-FRAME SCOPE\n"
    "Apply Filter Application across the complete already-resolved final frame as one post-process, including all "
    "characters, the complete background and environment, and resolved FX. This full-frame filter may change only "
    "the final image response. Do not add, remove, replace, relayout, or regenerate scene content, and do not change "
    "character identity or design, geometry, camera or framing, animation or timing, FX placement, or the established "
    "lighting direction. Then apply a clean Kodak 5245 negative-film response combined with a Kodak 2383 print-film response, "
    "using restrained film color correction at low strength and a very subtle cool printer-light bias leaning "
    "toward cyan-blue. Maintain a gently controlled input tonal response corresponding to gamma 1.2 and a clean "
    "output gamma response around 2.2. Add only a very subtle, nearly imperceptible highlight glow. Preserve clean "
    "local colors, controlled highlights, rich but readable shadows, and stable color separation. Do not introduce "
    "or simulate any film grain."
)


def _deep_patch(base: dict[str, Any], changes: Mapping[str, Any], path: str = "state") -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in changes.items():
        if key not in result:
            raise FinishLookValidationError(f"{path}.{key} is not a supported field.")
        if isinstance(result[key], dict):
            if not isinstance(value, Mapping):
                raise FinishLookValidationError(f"{path}.{key} must be an object.")
            result[key] = _deep_patch(result[key], value, f"{path}.{key}")
        else:
            result[key] = copy.deepcopy(value)
    return result


def normalize_remote_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FinishLookValidationError("remote request must be a dict object.")
    request = _mapping(value, "remote request")
    required = {"schema", "version", "request_id", "base_revision", "changes"}
    _exact_keys(request, required, "remote request")
    if request["schema"] != REMOTE_SCHEMA or type(request["version"]) is not int or request["version"] != 1:
        raise FinishLookValidationError("Unsupported remote request schema or version.")
    request_id = request["request_id"]
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > MAX_REQUEST_ID_LENGTH:
        raise FinishLookValidationError("remote request_id must be a non-empty bounded string.")
    revision = request["base_revision"]
    if type(revision) is not int or revision < 0:
        raise FinishLookValidationError("remote base_revision must be a non-negative integer.")
    if not isinstance(request["changes"], Mapping):
        raise FinishLookValidationError("remote changes must be a dict object.")
    changes = request["changes"]
    if not changes or any(key not in {"beauty", "film"} for key in changes):
        raise FinishLookValidationError("remote changes must contain only beauty and/or film.")
    return {
        "schema": REMOTE_SCHEMA,
        "version": 1,
        "request_id": request_id.strip(),
        "base_revision": revision,
        "changes": copy.deepcopy(dict(changes)),
    }


def apply_finish_look_remote_request(
    current_state: Mapping[str, Any],
    request: Any,
    *,
    current_revision: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    canonical = validate_finish_look_state(current_state)
    normalized = normalize_remote_request(request)
    request_id = normalized["request_id"]
    if normalized["base_revision"] != current_revision:
        return canonical, {
            "schema_version": 1,
            "status": "rejected",
            "code": "stale_revision",
            "message": f"Expected base_revision {current_revision}.",
            "request_id": request_id,
            "revision": current_revision,
        }
    patched = _deep_patch(canonical, normalized["changes"])
    validated = validate_finish_look_state(patched)
    return validated, {
        "schema_version": 1,
        "status": "accepted",
        "code": "ok",
        "message": "Finish Look state updated.",
        "request_id": request_id,
        "revision": current_revision + 1,
    }


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def default_widget_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "language": "ko",
        "remote_connected": False,
        "shot_catalog": {},
        "shot": _shot_only(),
        "finish_look": default_finish_look_state(),
        "catalog": film_stock_catalog_payload(),
    }


def validate_widget_state(value: Any) -> dict[str, Any]:
    state = _mapping(value, "widget state")
    required = {
        "schema_version",
        "language",
        "remote_connected",
        "finish_look",
        "catalog",
    }
    allowed = required | {
        "shot_catalog",
        "shot",
    }
    missing = sorted(required - set(state))
    unknown = sorted(set(state) - allowed)
    if missing:
        raise FinishLookValidationError(
            f"widget state is missing: {', '.join(missing)}."
        )
    if unknown:
        raise FinishLookValidationError(
            f"widget state contains unsupported keys: {', '.join(unknown)}."
        )
    if type(state["schema_version"]) is not int or state["schema_version"] != 1:
        raise FinishLookValidationError("widget schema_version must be integer 1.")
    language = _choice(state["language"], ("ko", "en"), "widget language")
    catalog = _mapping(state["catalog"], "widget catalog")
    if list(catalog.get("negative", [])) != list(NEGATIVE_FILM_STOCKS) or list(catalog.get("print", [])) != list(PRINT_FILM_STOCKS):
        raise FinishLookValidationError("widget Film Stock catalog does not match the backend catalog.")
    shot_catalog = _normalize_shot_catalog(
        state.get("shot_catalog"), allow_sparse=True
    )
    shot = _normalize_shot_selection(state.get("shot"), shot_catalog)
    return {
        "schema_version": 1,
        "language": language,
        "remote_connected": _boolean(state["remote_connected"], "widget remote_connected"),
        "shot_catalog": shot_catalog,
        "shot": shot,
        "finish_look": validate_finish_look_state(state["finish_look"]),
        "catalog": film_stock_catalog_payload(),
    }


def _mode(name: str) -> Any:
    if ParameterMode is None:
        return None
    return {getattr(ParameterMode, name)}


def _parameter_attempts(kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    modern = dict(kwargs)
    if modern.get("allowed_modes") is not None:
        for key in ("allow_input", "allow_output", "allow_property"):
            modern.pop(key, None)
    legacy = dict(kwargs)
    legacy.pop("allowed_modes", None)
    attempts: list[dict[str, Any]] = []
    for candidate in (modern, legacy):
        attempts.append(candidate)
        without_type = dict(candidate)
        without_type.pop("type", None)
        if without_type != candidate:
            attempts.append(without_type)
    return attempts


def _add_parameter(node: Any, **kwargs: Any) -> Any:
    if parameter_exists(node, str(kwargs.get("name") or "")):
        return getattr(node, "parameters", {}).get(kwargs["name"])
    last_error: Exception | None = None
    for attempt in _parameter_attempts(kwargs):
        try:
            parameter = Parameter(**attempt)
            node.add_parameter(parameter)
            return parameter
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError(f"Unable to add parameter {kwargs.get('name')}.")


def _parameter_object(node: Any, name: str) -> Any:
    for getter_name in ("get_parameter_by_name", "get_parameter"):
        getter = getattr(node, getter_name, None)
        if callable(getter):
            try:
                parameter = getter(name)
                if parameter is not None:
                    return parameter
            except Exception:
                pass
    parameters = getattr(node, "parameters", None)
    if isinstance(parameters, dict):
        return parameters.get(name)
    if isinstance(parameters, (list, tuple)):
        return next(
            (
                parameter
                for parameter in parameters
                if getattr(parameter, "name", None) == name
            ),
            None,
        )
    return None


def _add_widget_parameter(node: Any, *, widget_name: str, **kwargs: Any) -> Any:
    """Attach the Widget trait before Griptape performs its first row layout."""

    name = str(kwargs.get("name") or "")
    if parameter_exists(node, name):
        parameter = _parameter_object(node, name)
    else:
        parameter = None
        last_error: Exception | None = None
        for attempt in _parameter_attempts(kwargs):
            if Widget is not None:
                try:
                    parameter = Parameter(
                        **{
                            **attempt,
                            "traits": {
                                Widget(name=widget_name, library=WIDGET_LIBRARY_NAME)
                            },
                        }
                    )
                    break
                except Exception as exc:
                    last_error = exc
            try:
                parameter = Parameter(**attempt)
                if Widget is not None:
                    parameter.add_trait(
                        Widget(name=widget_name, library=WIDGET_LIBRARY_NAME)
                    )
                break
            except Exception as exc:
                parameter = None
                last_error = exc
        if parameter is None:
            raise last_error or RuntimeError(f"Unable to add widget parameter {name}.")
        # Adding the trait after add_parameter() leaves the host's first layout
        # cached as a compact native dict row (about 40-48 px).
        node.add_parameter(parameter)

    if Widget is not None and parameter is not None:
        has_widget = False
        try:
            finder = getattr(parameter, "find_elements_by_type", None)
            if callable(finder):
                has_widget = bool(finder(Widget, find_recursively=True))
        except Exception:
            has_widget = False
        if not has_widget:
            try:
                parameter.add_trait(
                    Widget(name=widget_name, library=WIDGET_LIBRARY_NAME)
                )
            except Exception:
                pass
    return parameter


def _apply_parameter_ui_options(parameter: Any, options: Mapping[str, Any]) -> None:
    if parameter is None:
        return
    try:
        current = dict(getattr(parameter, "ui_options", {}) or {})
        current.update(dict(options))
        parameter.ui_options = current
    except Exception:
        return
    updater = getattr(parameter, "update_ui_options_key", None)
    if callable(updater):
        for key, value in options.items():
            try:
                updater(key, value)
            except Exception:
                pass


def _hidden_transport_ui_options() -> dict[str, Any]:
    return {
        "display_name": "",
        "hide": True,
        "hide_property": True,
        "hide_label": True,
        "hide_handles": True,
        "height": 1,
        "min_height": 0,
        "max_height": 1,
        "is_full_width": True,
        "expandable": False,
        "compact": True,
    }


def _hide_transport_parameter(parameter: Any) -> None:
    if parameter is None:
        return
    for attribute in ("hide", "hide_property", "hide_label"):
        try:
            setattr(parameter, attribute, True)
        except Exception:
            pass
    _apply_parameter_ui_options(parameter, _hidden_transport_ui_options())


def _raw_parameter(node: Any, name: str) -> Any:
    try:
        return node.get_parameter_value(name)
    except Exception:
        parameter = getattr(node, "parameters", {}).get(name)
        return getattr(parameter, "default_value", None)


def _set_parameter_silently(node: Any, name: str, value: Any) -> None:
    parent_setter = getattr(super(type(node), node), "set_parameter_value", None)
    if callable(parent_setter):
        try:
            if ParameterMode is None:
                parent_setter(name, copy.deepcopy(value))
            else:
                parent_setter(
                    name,
                    copy.deepcopy(value),
                    initial_setup=False,
                    emit_change=False,
                    skip_before_value_set=True,
                )
            return
        except (AttributeError, TypeError):
            try:
                parent_setter(name, copy.deepcopy(value))
                return
            except Exception:
                pass
        except Exception:
            pass
    parameter = getattr(node, "parameters", {}).get(name)
    if parameter is not None:
        try:
            parameter.default_value = copy.deepcopy(value)
        except Exception:
            pass


class HMBFinishLookLibrary(DataNode):
    """Deterministic Character Beauty and Filter Application compiler with auxiliary video tools."""

    def __init__(self, **kwargs: Any) -> None:
        serialized_metadata = kwargs.get("metadata")
        restored_size = (
            dict(serialized_metadata.get("size") or {})
            if isinstance(serialized_metadata, dict)
            and isinstance(serialized_metadata.get("size"), dict)
            else {}
        )
        super().__init__(**kwargs)
        if restored_size:
            try:
                current_metadata = dict(getattr(self, "metadata", {}) or {})
                current_metadata["size"] = restored_size
                self.metadata = current_metadata
            except Exception:
                pass
        try:
            metadata = dict(getattr(self, "metadata", {}) or {})
            saved_size = metadata.get("size")
            try:
                has_saved_size = (
                    isinstance(saved_size, dict)
                    and float(saved_size.get("width") or 0) > 0
                    and float(saved_size.get("height") or 0) > 0
                )
            except (TypeError, ValueError):
                has_saved_size = False
            initial_size_setter = getattr(self, "set_initial_node_size", None)
            if not has_saved_size and callable(initial_size_setter):
                initial_size_setter(
                    width=FINISH_LOOK_NODE_WIDTH,
                    height=FINISH_LOOK_NODE_HEIGHT,
                )
            elif not has_saved_size:
                metadata.setdefault(
                    "size",
                    {
                        "width": FINISH_LOOK_NODE_WIDTH,
                        "height": FINISH_LOOK_NODE_HEIGHT,
                    },
                )
                self.metadata = metadata
            self.ui_options = {
                "width": FINISH_LOOK_NODE_WIDTH,
                "height": FINISH_LOOK_NODE_HEIGHT,
                "default_width": FINISH_LOOK_NODE_WIDTH,
                "default_height": FINISH_LOOK_NODE_HEIGHT,
                "preferred_width": FINISH_LOOK_NODE_WIDTH,
                "preferred_height": FINISH_LOOK_NODE_HEIGHT,
                "initial_width": FINISH_LOOK_NODE_WIDTH,
                "initial_height": FINISH_LOOK_NODE_HEIGHT,
                "node_size": {
                    "width": FINISH_LOOK_NODE_WIDTH,
                    "height": FINISH_LOOK_NODE_HEIGHT,
                },
                "default_size": {
                    "width": FINISH_LOOK_NODE_WIDTH,
                    "height": FINISH_LOOK_NODE_HEIGHT,
                },
                "initial_size": {
                    "width": FINISH_LOOK_NODE_WIDTH,
                    "height": FINISH_LOOK_NODE_HEIGHT,
                },
                "min_width": FINISH_LOOK_NODE_MIN_WIDTH,
                "min_height": FINISH_LOOK_NODE_MIN_HEIGHT,
                "resizable": True,
            }
            self.width = (
                saved_size.get("width") if has_saved_size else FINISH_LOOK_NODE_WIDTH
            )
            self.height = (
                saved_size.get("height") if has_saved_size else FINISH_LOOK_NODE_HEIGHT
            )
        except Exception:
            pass
        self.category = "HMB_GP_Production"
        self.description = (
            "Compiles character-matte-only Character Beauty and full-frame Filter Application values "
            "into deterministic English production prose."
        )
        self._state_lock = threading.RLock()
        self._last_valid_state = default_finish_look_state()
        self._widget_state = default_widget_state()
        self._remote_revision = 0
        self._remote_connected = False
        self._seen_remote_requests: list[str] = []
        self._remote_status = copy.deepcopy(DEFAULT_REMOTE_STATUS)
        self._node_deleted = False
        # Shared Shot routing excludes a node as soon as this flag is set,
        # including the short interval before retained mode removes it from
        # the flow registry.
        self._hmb_node_deleted = False
        self._delete_parent_called = False
        self._syncing_widget = False
        self._hmb_shot_catalog_snapshot: dict[str, Any] = {}
        self._hmb_shot_route_status: dict[str, Any] = {}
        self._hmb_shot_catalog_syncing = False
        self._hmb_initial_shot_autoclaim_pending = True
        self._hmb_initial_shot_preferred_uuid = ""
        self._hmb_finish_snapshot_generation = 0
        self._hmb_finish_snapshot_fingerprint = ""
        self._hmb_finish_snapshot_live_fingerprint = ""
        # A hidden Shot snapshot may publish only after the router has attached
        # the exact same-UUID Seedance edge.  Keep this false across
        # construction, hydration, and Shot changes so a stale edge can never
        # receive the next Shot's finishing instruction.
        self._hmb_finish_route_ready = False
        self._hmb_finish_snapshot: dict[str, Any] = {}
        self._setup_parameters()
        self._repair_ui_contract()
        self._publish_all(live=False)
        try:
            from _hmb_shot_routing import schedule_post_registration_reconcile

            schedule_post_registration_reconcile(self)
        except Exception:
            pass
        LOGGER.info("[HMB][FINISH] Finish Look initialized with schema version 1.")

    def _setup_parameters(self) -> None:
        add_group(self, "A_HMB_FINISH_LOOK", "HMB Finish Look", collapsed=False)
        widget_ui_options = {
            "display_name": "HMB Finish Look",
            "is_full_width": True,
            "height": FINISH_LOOK_WIDGET_HEIGHT,
            "min_height": FINISH_LOOK_WIDGET_MIN_HEIGHT,
            "widget_height": FINISH_LOOK_WIDGET_HEIGHT,
            "width": FINISH_LOOK_NODE_WIDTH,
            "min_width": FINISH_LOOK_NODE_MIN_WIDTH,
            "preferred_width": FINISH_LOOK_NODE_WIDTH,
            "preferred_height": FINISH_LOOK_WIDGET_HEIGHT,
            "default_width": FINISH_LOOK_NODE_WIDTH,
            "default_height": FINISH_LOOK_WIDGET_HEIGHT,
            "initial_width": FINISH_LOOK_NODE_WIDTH,
            "initial_height": FINISH_LOOK_WIDGET_HEIGHT,
            "node_size": {
                "width": FINISH_LOOK_NODE_WIDTH,
                "height": FINISH_LOOK_NODE_HEIGHT,
            },
            "default_size": {
                "width": FINISH_LOOK_NODE_WIDTH,
                "height": FINISH_LOOK_NODE_HEIGHT,
            },
            "initial_size": {
                "width": FINISH_LOOK_NODE_WIDTH,
                "height": FINISH_LOOK_NODE_HEIGHT,
            },
            # This is the sole visible Finish Look row. Keeping it expandable
            # prevents Griptape's first 40 px allocator pass from clipping the
            # dashboard to its header.
            "expandable": True,
            "resizable": True,
            "compact": False,
            "hide": False,
            "hide_property": False,
        }
        widget_parameter = _add_widget_parameter(
            self,
            widget_name=WIDGET_NAME,
            name=WIDGET_PARAMETER_NAME,
            default_value=default_widget_state(),
            type="dict",
            input_types=["dict"],
            allow_input=False,
            allow_output=False,
            allow_property=True,
            allowed_modes=_mode("PROPERTY"),
            tooltip=(
                "HMB Finish Look dashboard state. Character Beauty has one direct Enable switch, no value "
                "bundle selector, and applies only inside character mattes."
            ),
            ui_options=widget_ui_options,
        )
        for attribute, value in (
            ("hide", False),
            ("hide_property", False),
            ("serializable", True),
            ("settable", True),
        ):
            try:
                setattr(widget_parameter, attribute, value)
            except Exception:
                pass
        _apply_parameter_ui_options(widget_parameter, widget_ui_options)

        parameter = _add_parameter(
            self, name=REMOTE_INPUT_PARAMETER_NAME, default_value={}, type="dict",
            input_types=["dict"], allow_input=True, allow_output=False,
            allow_property=False, allowed_modes=_mode("INPUT"), hide_property=True,
            serializable=False, tooltip="Validated same-flow Finish Look remote patch input.",
            ui_options=_hidden_transport_ui_options(),
        )
        _hide_transport_parameter(parameter)
        outputs = (
            (
                FINISH_LOOK_OUTPUT_PARAMETER_NAME,
                "",
                "str",
                "Deterministic English Character Beauty and full-frame Filter Application prose.",
            ),
            (
                SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME,
                {},
                "dict",
                "Hidden same-Shot Finish Look dependency for HMBSeedanceGeneration.",
            ),
            (FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME, default_finish_look_state(), "dict", "Canonical schema_version 1 state."),
            (REMOTE_STATUS_OUTPUT_PARAMETER_NAME, copy.deepcopy(DEFAULT_REMOTE_STATUS), "dict", "Latest strict remote patch result."),
        )
        for name, default, type_name, tooltip in outputs:
            parameter = _add_parameter(
                self,
                name=name,
                default_value=default,
                type=type_name,
                output_type=type_name,
                input_types=[],
                allow_input=False,
                allow_output=True,
                allow_property=False,
                allowed_modes=_mode("OUTPUT"),
                settable=False,
                hide_property=True,
                tooltip=tooltip,
                ui_options=_hidden_transport_ui_options(),
            )
            _hide_transport_parameter(parameter)

    def _repair_ui_contract(self) -> None:
        """Reapply the host surface contract after saved-workflow hydration."""

        widget_parameter = _parameter_object(self, WIDGET_PARAMETER_NAME)
        if widget_parameter is not None:
            for attribute, value in (
                ("hide", False),
                ("hide_property", False),
                ("serializable", True),
                ("settable", True),
            ):
                try:
                    setattr(widget_parameter, attribute, value)
                except Exception:
                    pass
            _apply_parameter_ui_options(
                widget_parameter,
                {
                    "display_name": "HMB Finish Look",
                    "is_full_width": True,
                    "height": FINISH_LOOK_WIDGET_HEIGHT,
                    "min_height": FINISH_LOOK_WIDGET_MIN_HEIGHT,
                    "widget_height": FINISH_LOOK_WIDGET_HEIGHT,
                    "width": FINISH_LOOK_NODE_WIDTH,
                    "min_width": FINISH_LOOK_NODE_MIN_WIDTH,
                    "preferred_width": FINISH_LOOK_NODE_WIDTH,
                    "preferred_height": FINISH_LOOK_WIDGET_HEIGHT,
                    "default_width": FINISH_LOOK_NODE_WIDTH,
                    "default_height": FINISH_LOOK_WIDGET_HEIGHT,
                    "initial_width": FINISH_LOOK_NODE_WIDTH,
                    "initial_height": FINISH_LOOK_WIDGET_HEIGHT,
                    "node_size": {
                        "width": FINISH_LOOK_NODE_WIDTH,
                        "height": FINISH_LOOK_NODE_HEIGHT,
                    },
                    "default_size": {
                        "width": FINISH_LOOK_NODE_WIDTH,
                        "height": FINISH_LOOK_NODE_HEIGHT,
                    },
                    "initial_size": {
                        "width": FINISH_LOOK_NODE_WIDTH,
                        "height": FINISH_LOOK_NODE_HEIGHT,
                    },
                    "expandable": True,
                    "resizable": True,
                    "compact": False,
                    "hide": False,
                    "hide_property": False,
                },
            )
        for name in (
            REMOTE_INPUT_PARAMETER_NAME,
            FINISH_LOOK_OUTPUT_PARAMETER_NAME,
            SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME,
            FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME,
            REMOTE_STATUS_OUTPUT_PARAMETER_NAME,
        ):
            _hide_transport_parameter(_parameter_object(self, name))

    def _publish_parameter(self, name: str, value: Any, *, live: bool) -> bool:
        set_output(self, name, copy.deepcopy(value))
        if not live:
            return True
        publisher = getattr(self, "publish_update_to_parameter", None)
        if not callable(publisher):
            return False
        try:
            publisher(name, copy.deepcopy(value))
        except Exception:
            return False
        return True

    def _update_finish_snapshot_locked(
        self,
        prompt: str,
        state: Mapping[str, Any],
    ) -> bool:
        subscription = self._hmb_shot_channel_subscription()
        if not subscription.get("enabled"):
            changed = bool(self._hmb_finish_snapshot)
            self._hmb_finish_snapshot = {}
            self._hmb_finish_snapshot_fingerprint = ""
            return changed
        identity = {
            "channel_uuid": subscription.get("channel_uuid", ""),
            "shot_uuid": subscription.get("shot_uuid", ""),
            "shot_number": subscription.get("shot_number", 1),
            "shot_name": subscription.get("shot_name", "Only"),
        }
        state_sha256 = hashlib.sha256(
            json.dumps(
                state,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    **identity,
                    "state_sha256": state_sha256,
                    "instruction_sha256": prompt_sha256,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        changed = fingerprint != self._hmb_finish_snapshot_fingerprint
        if changed:
            self._hmb_finish_snapshot_generation += 1
            self._hmb_finish_snapshot_fingerprint = fingerprint
        self._hmb_finish_snapshot = {
            "schema": FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA,
            "version": FINISH_LOOK_SHOT_SNAPSHOT_VERSION,
            **identity,
            "generation": max(1, self._hmb_finish_snapshot_generation),
            "finish_look_sha256": prompt_sha256,
            "state_sha256": state_sha256,
            "finish_look_out": prompt,
        }
        return changed

    def _publish_all(self, *, live: bool) -> None:
        with self._state_lock:
            state = copy.deepcopy(self._last_valid_state)
            prompt = compile_finish_look_prompt(state)
            self._update_finish_snapshot_locked(prompt, state)
            shot_snapshot = copy.deepcopy(self._hmb_finish_snapshot)
            shot_fingerprint = self._hmb_finish_snapshot_fingerprint
            publish_shot_snapshot = (
                self._hmb_finish_route_ready
                and bool(shot_snapshot)
                and shot_fingerprint != self._hmb_finish_snapshot_live_fingerprint
            )
            remote_status = copy.deepcopy(self._remote_status)
        # Stage the sibling values before any live publication can wake a consumer.
        values = (
            (FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME, state),
            (FINISH_LOOK_OUTPUT_PARAMETER_NAME, prompt),
            (SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME, shot_snapshot),
            (REMOTE_STATUS_OUTPUT_PARAMETER_NAME, remote_status),
        )
        for name, value in values:
            set_output(self, name, copy.deepcopy(value))
        if live:
            for name, value in values:
                if name == SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME:
                    if publish_shot_snapshot:
                        if self._publish_parameter(name, value, live=True):
                            with self._state_lock:
                                self._hmb_finish_snapshot_live_fingerprint = shot_fingerprint
                    continue
                self._publish_parameter(name, value, live=True)

    def _restore_widget_parameter(self, *, live: bool = False) -> None:
        shot_catalog = _normalize_shot_catalog(
            self._widget_state.get("shot_catalog"), allow_sparse=True
        )
        shot = _normalize_shot_selection(
            self._widget_state.get("shot"), shot_catalog
        )
        self._widget_state = {
            "schema_version": 1,
            "language": self._widget_state.get("language", "ko"),
            "remote_connected": self._remote_connected,
            "shot_catalog": shot_catalog,
            "shot": shot,
            "finish_look": copy.deepcopy(self._last_valid_state),
            "catalog": film_stock_catalog_payload(),
            }
        try:
            self._syncing_widget = True
            _set_parameter_silently(self, WIDGET_PARAMETER_NAME, self._widget_state)
            if live:
                publisher = getattr(self, "publish_update_to_parameter", None)
                if callable(publisher):
                    publisher(WIDGET_PARAMETER_NAME, copy.deepcopy(self._widget_state))
        except Exception:
            pass
        finally:
            self._syncing_widget = False

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        """Return the exact Shot identity owned by this Finish Look node."""

        shot = (
            self._widget_state.get("shot", {})
            if isinstance(self._widget_state, Mapping)
            else {}
        )
        normalized = _normalize_shot_selection(
            shot,
            self._widget_state.get("shot_catalog", {})
            if isinstance(self._widget_state, Mapping)
            else {},
        )
        deleted = bool(
            getattr(self, "_hmb_node_deleted", False)
            or getattr(self, "_node_deleted", False)
        )
        enabled = bool(
            not deleted
            and normalized["channel_uuid"]
            and normalized["shot_uuid"]
        )
        return {
            "schema": SHOT_SUBSCRIPTION_SCHEMA,
            "version": SHOT_SUBSCRIPTION_VERSION,
            "participant_kind": "finish_look",
            "enabled": enabled,
            "channel_uuid": normalized["channel_uuid"] if enabled else "",
            "shot_uuid": normalized["shot_uuid"] if enabled else "",
            "shot_number": normalized["number"] if enabled else 1,
            "shot_name": normalized["name"] if enabled else "Only",
        }

    def _hmb_prepare_initial_shot_selection(self, shot_uuid: Any = "") -> None:
        """Remember one router-proven, unclaimed Shot for initial adoption."""

        if not bool(getattr(self, "_hmb_initial_shot_autoclaim_pending", False)):
            return
        if self._hmb_shot_channel_subscription().get("enabled"):
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
            return
        self._hmb_initial_shot_preferred_uuid = str(shot_uuid or "").strip()[:128]

    def _hmb_available_finish_shot_catalog(
        self,
        snapshot: Any,
        current_shot: Any = None,
    ) -> dict[str, Any]:
        """Hide Shots already owned by another live Finish Look node."""

        normalized = _normalize_shot_catalog(snapshot)
        if not normalized:
            return {}
        current = (
            current_shot
            if isinstance(current_shot, Mapping)
            else self._hmb_shot_channel_subscription()
        )
        current_uuid = (
            str(current.get("shot_uuid") or "")
            if current.get("channel_uuid") == normalized["channel_uuid"]
            else ""
        )
        claimed: set[str] = set()
        try:
            from _hmb_shot_routing import _same_flow_nodes

            _flow_name, nodes = _same_flow_nodes(self)
        except Exception:
            nodes = []
        for candidate in nodes:
            if candidate is self or bool(getattr(candidate, "_hmb_node_deleted", False)):
                continue
            getter = getattr(candidate, "_hmb_shot_channel_subscription", None)
            if not callable(getter):
                continue
            try:
                subscription = getter()
            except Exception:
                continue
            if (
                isinstance(subscription, Mapping)
                and subscription.get("participant_kind") == "finish_look"
                and subscription.get("enabled") is True
                and subscription.get("channel_uuid") == normalized["channel_uuid"]
                and subscription.get("shot_uuid")
            ):
                claimed.add(str(subscription["shot_uuid"]))
        shots = [
            dict(item)
            for item in normalized["shots"]
            if item["shot_uuid"] not in claimed or item["shot_uuid"] == current_uuid
        ]
        if not shots:
            return {}
        metadata_sha256 = hashlib.sha256(
            json.dumps(
                {
                    "channel_uuid": normalized["channel_uuid"],
                    "generation": normalized["generation"],
                    "shots": shots,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        # This is a bounded node-local selector projection. The original
        # authenticated catalog remains in _hmb_shot_catalog_snapshot.
        return {**normalized, "metadata_sha256": metadata_sha256, "shots": shots}

    def _hmb_reconcile_shot_routing(self, snapshot: Any) -> None:
        """Adopt one UUID-backed Shot without changing authored look values."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        normalized = _normalize_shot_catalog(snapshot, strict=True)
        previous = self._hmb_shot_catalog_snapshot
        if (
            isinstance(previous, Mapping)
            and previous.get("channel_uuid") == normalized["channel_uuid"]
        ):
            previous_generation = int(previous.get("generation") or 0)
            if normalized["generation"] < previous_generation:
                raise FinishLookValidationError("Shot catalog generation moved backwards.")
            if (
                normalized["generation"] == previous_generation
                and normalized["metadata_sha256"] != previous.get("metadata_sha256")
            ):
                raise FinishLookValidationError(
                    "Shot catalog changed without a new generation."
                )
        self._hmb_shot_catalog_snapshot = copy.deepcopy(normalized)
        current = self._hmb_shot_channel_subscription()
        available = self._hmb_available_finish_shot_catalog(normalized, current)
        available_shots = available.get("shots", []) if available else []
        selected = next(
            (
                item
                for item in available_shots
                if item["shot_uuid"] == current.get("shot_uuid")
            ),
            None,
        )
        initial_autoclaim = bool(
            selected is None
            and not current.get("enabled")
            and getattr(self, "_hmb_initial_shot_autoclaim_pending", False)
            and getattr(self, "_hmb_initial_shot_preferred_uuid", "")
        )
        if initial_autoclaim:
            preferred_uuid = str(self._hmb_initial_shot_preferred_uuid)
            selected = next(
                (item for item in available_shots if item["shot_uuid"] == preferred_uuid),
                None,
            )
        shot = (
            {
                "channel_uuid": normalized["channel_uuid"],
                "shot_uuid": selected["shot_uuid"],
                "number": selected["number"],
                "name": selected["name"],
            }
            if isinstance(selected, Mapping)
            else _shot_only()
        )
        current_identity = {
            "channel_uuid": str(current.get("channel_uuid") or ""),
            "shot_uuid": str(current.get("shot_uuid") or ""),
            "number": int(current.get("shot_number") or 1),
            "name": str(current.get("shot_name") or "Only"),
        }
        shot_route_changed = (
            str(shot.get("channel_uuid") or ""),
            str(shot.get("shot_uuid") or ""),
        ) != (
            str(current_identity.get("channel_uuid") or ""),
            str(current_identity.get("shot_uuid") or ""),
        )
        if shot != current_identity:
            # The previous retained edge may still exist until this routing
            # transaction completes. Stage the new identity without waking
            # that edge with a cross-Shot finishing instruction.
            self._hmb_finish_route_ready = False
        if initial_autoclaim:
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
        with self._state_lock:
            self._hmb_shot_catalog_syncing = True
            try:
                self._widget_state["shot_catalog"] = copy.deepcopy(available)
                self._widget_state["shot"] = shot
                self._restore_widget_parameter(live=True)
            finally:
                self._hmb_shot_catalog_syncing = False
        # Catalog delivery precedes retained-edge mutation. Stage the new
        # snapshot without waking the previously connected Shot; the router
        # will attach the staged value to the new exact UUID owner.
        self._publish_all(live=False)
        self._hmb_shot_route_status = {
            "ok": True,
            "code": "catalog_ready" if shot["shot_uuid"] else "only",
        }

    def _hmb_clear_shot_routing_catalog(
        self,
        reason: str = "publisher_unavailable",
    ) -> dict[str, Any]:
        """Return to Only while retaining Character Beauty and Filter Application."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return self._hmb_shot_channel_subscription()
        with self._state_lock:
            self._hmb_shot_catalog_snapshot = {}
            self._hmb_finish_route_ready = False
            self._widget_state["shot_catalog"] = {}
            self._widget_state["shot"] = _shot_only()
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
            self._restore_widget_parameter(live=True)
        self._publish_all(live=False)
        self._hmb_shot_route_status = {
            "ok": False,
            "code": str(reason or "publisher_unavailable")[:128],
        }
        return self._hmb_shot_channel_subscription()

    def _hmb_reject_duplicate_shot_selection(
        self,
        reason: str = "duplicate_finish_look_shot",
    ) -> dict[str, Any]:
        """Release a duplicate Shot claim but retain available selector choices."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return self._hmb_shot_channel_subscription()
        available = self._hmb_available_finish_shot_catalog(
            self._hmb_shot_catalog_snapshot,
            {},
        )
        with self._state_lock:
            self._hmb_finish_route_ready = False
            self._widget_state["shot_catalog"] = copy.deepcopy(available)
            self._widget_state["shot"] = _shot_only()
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
            self._restore_widget_parameter(live=True)
        self._publish_all(live=False)
        self._hmb_shot_route_status = {
            "ok": False,
            "code": str(reason or "duplicate_finish_look_shot")[:128],
        }
        return self._hmb_shot_channel_subscription()

    def _hmb_shot_routing_status(self, value: Any) -> None:
        if not bool(getattr(self, "_hmb_node_deleted", False)) and isinstance(value, Mapping):
            self._hmb_shot_route_status = dict(value)

    def _reconcile_shared_shot_routing(self, *, strict: bool = False) -> dict[str, Any]:
        try:
            from _hmb_shot_routing import reconcile_shot_routing

            result = reconcile_shot_routing(self)
        except Exception:
            if strict and self._hmb_shot_channel_subscription().get("enabled"):
                raise RuntimeError("Finish Look Shot routing is unavailable.") from None
            return {"ok": False, "code": "unavailable", "changed": 0}
        if strict and self._hmb_shot_channel_subscription().get("enabled"):
            prefix = str(getattr(self, "name", "") or "") + ":"
            failures = result.get("failures", ()) if isinstance(result, Mapping) else ()
            if any(str(item).startswith(prefix) for item in failures):
                raise RuntimeError("Finish Look Shot routing is incomplete or ambiguous.")
        return dict(result) if isinstance(result, Mapping) else {
            "ok": False,
            "code": "invalid_result",
            "changed": 0,
        }

    def _hmb_post_registration_shot_discovery(self) -> None:
        if not bool(getattr(self, "_hmb_node_deleted", False)):
            self._reconcile_shared_shot_routing()

    def _hmb_finish_look_shot_snapshot(self, expected_output: Any = None) -> dict[str, Any]:
        """Return a validated atomic Finish Look snapshot for Seedance."""

        with self._state_lock:
            prompt = compile_finish_look_prompt(self._last_valid_state)
            self._update_finish_snapshot_locked(prompt, self._last_valid_state)
            snapshot = copy.deepcopy(self._hmb_finish_snapshot)
        required = {
            "schema",
            "version",
            "channel_uuid",
            "shot_uuid",
            "shot_number",
            "shot_name",
            "generation",
            "finish_look_sha256",
            "state_sha256",
            "finish_look_out",
        }
        if not snapshot or set(snapshot) != required:
            raise RuntimeError("Finish Look Shot snapshot is unavailable.")
        if expected_output is not None and expected_output != snapshot:
            raise RuntimeError("Finish Look hidden output does not match its atomic snapshot.")
        if not hmac.compare_digest(
            snapshot["finish_look_sha256"],
            hashlib.sha256(snapshot["finish_look_out"].encode("utf-8")).hexdigest(),
        ):
            raise RuntimeError("Finish Look instruction hash does not match.")
        return snapshot

    def _hmb_publish_routed_finish_snapshot(self, *, force: bool = False) -> bool:
        """Publish once after the router has attached the exact Seedance edge."""

        if not self._hmb_shot_channel_subscription().get("enabled"):
            with self._state_lock:
                self._hmb_finish_route_ready = False
            return False
        with self._state_lock:
            prompt = compile_finish_look_prompt(self._last_valid_state)
            self._update_finish_snapshot_locked(prompt, self._last_valid_state)
            snapshot = copy.deepcopy(self._hmb_finish_snapshot)
            fingerprint = self._hmb_finish_snapshot_fingerprint
            needs_publication = bool(
                force
                or not self._hmb_finish_route_ready
                or fingerprint != self._hmb_finish_snapshot_live_fingerprint
            )
        set_output(self, SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME, snapshot)
        if needs_publication:
            published = self._publish_parameter(
                SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME,
                snapshot,
                live=True,
            )
            if not published:
                with self._state_lock:
                    self._hmb_finish_route_ready = False
                return False
        with self._state_lock:
            self._hmb_finish_snapshot_live_fingerprint = fingerprint
            self._hmb_finish_route_ready = True
        return True

    def _record_bounded(self, target: list[str], identifier: str) -> None:
        target.append(identifier)
        if len(target) > MAX_REMOTE_HISTORY:
            del target[: len(target) - MAX_REMOTE_HISTORY]

    def _apply_widget_value(self, value: Any) -> None:
        try:
            normalized = validate_widget_state(value)
        except FinishLookValidationError as exc:
            with self._state_lock:
                self._remote_status = {
                    "schema_version": 1,
                    "status": "rejected",
                    "code": "invalid_ui_state",
                    "message": str(exc),
                    "request_id": "",
                    "revision": self._remote_revision,
                }
                self._restore_widget_parameter(live=True)
            self._publish_all(live=True)
            return
        remote_locked_rejected = False
        shot_changed = False
        with self._state_lock:
            previous_shot = _normalize_shot_selection(
                self._widget_state.get("shot"),
                self._widget_state.get("shot_catalog"),
            )
            authoritative_catalog = self._hmb_available_finish_shot_catalog(
                self._hmb_shot_catalog_snapshot,
                previous_shot,
            )
            # Before the first live catalog arrives, retain a serialized
            # catalog long enough for UUID-based hydration. Once routing owns
            # a catalog, browser state can never replace it.
            effective_catalog = authoritative_catalog or normalized["shot_catalog"]
            requested_shot = _normalize_shot_selection(
                normalized.get("shot"),
                effective_catalog,
            )
            shot_changed = requested_shot != previous_shot
            requested_state = copy.deepcopy(normalized["finish_look"])
            state_changed = requested_state != self._last_valid_state
            if self._remote_connected and state_changed:
                remote_locked_rejected = True
                requested_state = copy.deepcopy(self._last_valid_state)
                self._remote_status = {
                    "schema_version": 1,
                    "status": "rejected",
                    "code": "remote_locked",
                    "message": "Finish Look controls are locked while REMOTE is connected.",
                    "request_id": "",
                    "revision": self._remote_revision,
                }
            elif state_changed:
                self._remote_revision += 1
                self._remote_status = {
                    "schema_version": 1,
                    "status": "local_update",
                    "code": "ok",
                    "message": "Finish Look state updated locally.",
                    "request_id": "",
                    "revision": self._remote_revision,
                }
            self._last_valid_state = requested_state
            self._widget_state = copy.deepcopy(normalized)
            self._widget_state["shot_catalog"] = copy.deepcopy(effective_catalog)
            self._widget_state["shot"] = requested_shot
            if shot_changed:
                self._hmb_finish_route_ready = False
                self._hmb_initial_shot_autoclaim_pending = False
                self._hmb_initial_shot_preferred_uuid = ""
            self._restore_widget_parameter(live=remote_locked_rejected)
        if shot_changed and not self._hmb_shot_catalog_syncing:
            self._publish_all(live=False)
            self._reconcile_shared_shot_routing()
            self._publish_all(live=True)
        else:
            self._publish_all(live=True)

    def _apply_remote_value(self, value: Any, *, report_duplicate: bool = True) -> None:
        if not value:
            return
        request_id = ""
        try:
            normalized_request = normalize_remote_request(value)
            request_id = normalized_request["request_id"]
            with self._state_lock:
                if request_id in self._seen_remote_requests:
                    if report_duplicate:
                        self._remote_status = {
                            "schema_version": 1,
                            "status": "duplicate",
                            "code": "duplicate_request",
                            "message": "Remote request was already applied.",
                            "request_id": request_id,
                            "revision": self._remote_revision,
                        }
                    else:
                        return
                else:
                    next_state, status = apply_finish_look_remote_request(
                        self._last_valid_state,
                        normalized_request,
                        current_revision=self._remote_revision,
                    )
                    self._remote_status = status
                    self._record_bounded(self._seen_remote_requests, request_id)
                    if status["status"] == "accepted":
                        self._last_valid_state = next_state
                        self._remote_revision = int(status["revision"])
                        self._restore_widget_parameter(live=True)
        except FinishLookValidationError as exc:
            with self._state_lock:
                self._remote_status = {
                    "schema_version": 1,
                    "status": "rejected",
                    "code": "invalid_request",
                    "message": str(exc),
                    "request_id": request_id,
                    "revision": self._remote_revision,
                }
        self._publish_all(live=True)

    def after_value_set(self, parameter: Any, value: Any) -> Any:
        parent = getattr(super(), "after_value_set", None)
        result = parent(parameter, value) if callable(parent) else None
        if self._node_deleted:
            return result
        name = str(getattr(parameter, "name", "") or "")
        if name == WIDGET_PARAMETER_NAME and not self._syncing_widget:
            self._apply_widget_value(value)
        elif name == REMOTE_INPUT_PARAMETER_NAME:
            self._apply_remote_value(value)
        return result

    def after_incoming_connection(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        parent = getattr(super(), "after_incoming_connection", None)
        result = (
            parent(source_node, source_parameter, target_parameter)
            if callable(parent)
            else None
        )
        if str(getattr(target_parameter, "name", "") or "") == REMOTE_INPUT_PARAMETER_NAME:
            with self._state_lock:
                self._remote_connected = True
                self._restore_widget_parameter(live=True)
            self._publish_all(live=True)
        return result

    def after_incoming_connection_removed(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        parent = getattr(super(), "after_incoming_connection_removed", None)
        result = (
            parent(source_node, source_parameter, target_parameter)
            if callable(parent)
            else None
        )
        if str(getattr(target_parameter, "name", "") or "") == REMOTE_INPUT_PARAMETER_NAME:
            with self._state_lock:
                self._remote_connected = False
                self._restore_widget_parameter(live=True)
            self._publish_all(live=True)
        return result

    def before_value_set(self, parameter: Any, value: Any) -> Any:
        name = str(getattr(parameter, "name", "") or "")
        normalized = value
        if name == WIDGET_PARAMETER_NAME:
            try:
                normalized = validate_widget_state(value)
            except FinishLookValidationError as exc:
                with self._state_lock:
                    self._remote_status = {
                        "schema_version": 1,
                        "status": "rejected",
                        "code": "invalid_ui_state",
                        "message": str(exc),
                        "request_id": "",
                        "revision": self._remote_revision,
                    }
                    normalized = copy.deepcopy(self._widget_state)
        # Remote patch envelopes are deliberately validated in
        # the post-set handlers. This lets malformed input publish a rejected
        # status without throwing out of the host's value-set lifecycle.
        parent = getattr(super(), "before_value_set", None)
        if callable(parent):
            parent_value = parent(parameter, normalized)
            if parent_value is not None:
                normalized = parent_value
        return normalized

    def after_deserialize(self, *args: Any, **kwargs: Any) -> Any:
        parent = getattr(super(), "after_deserialize", None)
        result = parent(*args, **kwargs) if callable(parent) else None
        self._repair_ui_contract()
        value = _raw_parameter(self, WIDGET_PARAMETER_NAME)
        persisted = value if isinstance(value, Mapping) else {}
        persisted_shot = persisted.get("shot") if isinstance(persisted, Mapping) else {}
        if isinstance(persisted_shot, Mapping) and persisted_shot.get("shot_uuid"):
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
        self._apply_widget_value(value)
        try:
            from _hmb_shot_routing import schedule_post_hydration_reconcile

            schedule_post_hydration_reconcile(self)
        except Exception:
            pass
        return result

    def process(self) -> None:
        if self._node_deleted:
            return None
        remote_value = _raw_parameter(self, REMOTE_INPUT_PARAMETER_NAME)
        if remote_value:
            self._apply_remote_value(remote_value, report_duplicate=False)
        self._publish_all(live=False)
        LOGGER.info("[HMB][FINISH] FINISH_LOOK_OUT compiled.")
        return None

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        if self._delete_parent_called:
            return None
        self._node_deleted = True
        self._hmb_node_deleted = True
        self._hmb_finish_route_ready = False
        try:
            from _hmb_shot_routing import (
                prepare_node_deletion,
                release_node_lifecycle,
                schedule_post_deletion_reconcile,
            )

            prepare_node_deletion(self)
            release_node_lifecycle(self)
            schedule_post_deletion_reconcile(self)
        except Exception:
            pass
        self._delete_parent_called = True
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None


__all__ = [
    "DEFAULT_FINISH_LOOK_STATE",
    "EPSILON",
    "EXPECTED_DEFAULT_FINISH_LOOK_OUT",
    "FILM_STOCK_CATALOG",
    "FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA",
    "FINISH_LOOK_SHOT_SNAPSHOT_VERSION",
    "SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME",
    "HMBFinishLookLibrary",
    "NEGATIVE_FILM_STOCKS",
    "PRINT_FILM_STOCKS",
    "REVERSAL_FILM_STOCKS",
    "analyze_printer_lights",
    "apply_finish_look_remote_request",
    "compile_beauty_glow_prompt",
    "compile_beauty_prompt",
    "compile_exposure_prompt",
    "compile_film_glow_prompt",
    "compile_film_prompt",
    "compile_film_soft_focus_prompt",
    "compile_film_stock_prompt",
    "compile_finish_look_prompt",
    "compile_gamma_prompt",
    "compile_printer_lights_prompt",
    "compile_scale_cc_prompt",
    "compile_vignette_prompt",
    "default_finish_look_state",
    "default_widget_state",
    "film_stock_catalog_payload",
    "format_number",
    "is_zero",
    "join_sentences",
    "normalize_remote_request",
    "parse_finish_look_state",
    "validate_finish_look_state",
    "validate_widget_state",
]
