from __future__ import annotations

import os
import uuid
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


PROFILE = "hmb_screen_space_pattern_post_v2"
PHASE = "frame_top_left"
PATTERN_LINEAR_SCALE_DIVISOR = 3
BASE_CELL_DIVISOR = 8
SCALED_CELL_DIVISOR = BASE_CELL_DIVISOR * PATTERN_LINEAR_SCALE_DIVISOR
MIN_CELL_PIXELS = 4
POSITION_PATTERN_REPEATS = PATTERN_LINEAR_SCALE_DIVISOR
PATTERN_NAMES = (
    "direction_checker",
    "sky_grid",
    "floor_grid",
    "position_pattern",
)


class ScreenSpacePatternError(RuntimeError):
    """Raised when categorical marker frames cannot be processed safely."""


_PIL_MODULES: tuple[Any, Any, Any, type[BaseException], str] | None = None
_EQUALITY_LUTS: dict[int, tuple[int, ...]] = {}


def _require_pillow() -> tuple[Any, Any, Any, type[BaseException], str]:
    global _PIL_MODULES
    if _PIL_MODULES is not None:
        return _PIL_MODULES
    try:
        import PIL
        from PIL import Image, ImageChops, ImageDraw, UnidentifiedImageError
    except Exception as exc:
        raise ScreenSpacePatternError(
            "Screen-space pattern processing requires Pillow in the Griptape "
            "engine Python environment."
        ) from exc
    _PIL_MODULES = (
        Image,
        ImageChops,
        ImageDraw,
        UnidentifiedImageError,
        str(getattr(PIL, "__version__", "")),
    )
    return _PIL_MODULES


def preflight_pillow() -> dict[str, Any]:
    """Load Pillow on demand and report the available runtime."""

    _image, _chops, _draw, _unidentified, version = _require_pillow()
    return {
        "available": True,
        "version": version,
        "lazy": True,
    }


def _validated_rgb(value: Any, label: str) -> tuple[int, int, int]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != 3
    ):
        raise ScreenSpacePatternError(
            f"{label} must contain exactly three integer channels."
        )
    channels: list[int] = []
    for channel in value:
        if isinstance(channel, bool) or not isinstance(channel, int):
            raise ScreenSpacePatternError(
                f"{label} channels must be integers in the range 0..255."
            )
        if channel < 0 or channel > 255:
            raise ScreenSpacePatternError(
                f"{label} channels must be integers in the range 0..255."
            )
        channels.append(channel)
    return channels[0], channels[1], channels[2]


def _pattern_rows(catalog: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = catalog.get("background")
    if not isinstance(rows, list):
        raise ScreenSpacePatternError(
            "Marker catalog background rows must be a list."
        )
    return [
        row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("kind") or "").strip() == "pattern"
    ]


def validate_pattern_catalog(
    catalog: Mapping[str, Any],
) -> dict[str, tuple[int, int, int]]:
    """Return the unique categorical RGB assigned to every supported pattern."""

    if not isinstance(catalog, Mapping):
        raise ScreenSpacePatternError("Marker catalog must be a mapping.")

    found: dict[str, tuple[int, int, int]] = {}
    used_rgb: dict[tuple[int, int, int], str] = {}
    for row in _pattern_rows(catalog):
        pattern = str(row.get("pattern") or "").strip()
        if pattern not in PATTERN_NAMES:
            raise ScreenSpacePatternError(
                f"Unsupported screen-space pattern in marker catalog: {pattern or '<blank>'}"
            )
        if pattern in found:
            raise ScreenSpacePatternError(
                f"Duplicate screen-space pattern in marker catalog: {pattern}"
            )
        rgb = _validated_rgb(
            row.get("screen_space_id_rgb"),
            f"{pattern}.screen_space_id_rgb",
        )
        prior = used_rgb.get(rgb)
        if prior is not None:
            raise ScreenSpacePatternError(
                f"Pattern ID RGB {rgb} is shared by {prior} and {pattern}."
            )
        found[pattern] = rgb
        used_rgb[rgb] = pattern

    missing = [name for name in PATTERN_NAMES if name not in found]
    if missing:
        raise ScreenSpacePatternError(
            "Marker catalog is missing screen-space patterns: " + ", ".join(missing)
        )
    return {name: found[name] for name in PATTERN_NAMES}


def active_patterns_from_bindings(
    bindings: Iterable[Mapping[str, Any]] | None,
    catalog: Mapping[str, Any],
) -> tuple[str, ...]:
    """Resolve enabled pattern names from Picker Group Name + Color Pick rows."""

    validate_pattern_catalog(catalog)
    color_to_pattern: dict[str, str] = {}
    for row in _pattern_rows(catalog):
        color_name = str(row.get("name") or "").strip()
        pattern = str(row.get("pattern") or "").strip()
        if not color_name:
            raise ScreenSpacePatternError(
                f"Pattern catalog row has no display name: {pattern}"
            )
        if color_name in color_to_pattern:
            raise ScreenSpacePatternError(
                f"Duplicate marker display name in pattern catalog: {color_name}"
            )
        color_to_pattern[color_name] = pattern

    active: set[str] = set()
    if bindings is not None:
        for binding in bindings:
            if not isinstance(binding, Mapping):
                continue
            if not bool(binding.get("enabled", True)):
                continue
            color_name = str(binding.get("color") or "").strip()
            pattern = color_to_pattern.get(color_name)
            if pattern is not None:
                active.add(pattern)
    return tuple(name for name in PATTERN_NAMES if name in active)


def _validated_size(value: Sequence[int]) -> tuple[int, int]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != 2
    ):
        raise ScreenSpacePatternError(
            "expected_size must be a (width, height) integer pair."
        )
    width, height = value
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
    ):
        raise ScreenSpacePatternError(
            "expected_size must be a positive (width, height) integer pair."
        )
    return width, height


def _frame_paths(value: Iterable[os.PathLike[str] | str] | os.PathLike[str] | str) -> tuple[Path, ...]:
    if isinstance(value, (str, os.PathLike)):
        return (Path(value),)
    return tuple(Path(item) for item in value)


def _equality_lut(channel: int) -> tuple[int, ...]:
    lut = _EQUALITY_LUTS.get(channel)
    if lut is None:
        lut = tuple(255 if value == channel else 0 for value in range(256))
        _EQUALITY_LUTS[channel] = lut
    return lut


def _exact_rgb_mask(rgb_image: Any, rgb: tuple[int, int, int], image_chops: Any) -> Any:
    red, green, blue = rgb_image.split()
    red_match = green_match = blue_match = red_green = None
    try:
        red_match = red.point(_equality_lut(rgb[0]))
        green_match = green.point(_equality_lut(rgb[1]))
        blue_match = blue.point(_equality_lut(rgb[2]))
        red_green = image_chops.multiply(red_match, green_match)
        return image_chops.multiply(red_green, blue_match)
    finally:
        red.close()
        green.close()
        blue.close()
        for temporary in (red_match, green_match, blue_match, red_green):
            if temporary is not None:
                temporary.close()


def pattern_cell_size(size: Sequence[int]) -> int:
    """Return the fixed screen-space cell size for the three grid patterns."""

    width, height = _validated_size(size)
    return max(MIN_CELL_PIXELS, min(width, height) // SCALED_CELL_DIVISOR)


def _bounded_line_width(step: int, preferred: int) -> int:
    return max(1, min(preferred, max(1, step // 2)))


def _draw_direction_checker(image: Any, image_draw: Any) -> None:
    width, height = image.size
    tile = pattern_cell_size((width, height))
    draw = image_draw.Draw(image)
    for y_index, y in enumerate(range(0, height, tile)):
        for x_index, x in enumerate(range(0, width, tile)):
            if (x_index + y_index) % 2:
                draw.rectangle(
                    (
                        x,
                        y,
                        min(width - 1, x + tile - 1),
                        min(height - 1, y + tile - 1),
                    ),
                    fill=(255, 255, 255),
                )


def _draw_sky_grid(image: Any, image_draw: Any) -> None:
    width, height = image.size
    step = pattern_cell_size((width, height))
    major = step * 4
    minor_width = _bounded_line_width(step, 2)
    major_width = _bounded_line_width(step, 4)
    draw = image_draw.Draw(image)
    for x in range(0, width, step):
        draw.rectangle(
            (x, 0, min(width - 1, x + minor_width - 1), height - 1),
            fill=(191, 242, 255),
        )
    for y in range(0, height, step):
        draw.rectangle(
            (0, y, width - 1, min(height - 1, y + minor_width - 1)),
            fill=(191, 242, 255),
        )
    for x in range(0, width, major):
        draw.rectangle(
            (x, 0, min(width - 1, x + major_width - 1), height - 1),
            fill=(255, 255, 255),
        )
    for y in range(0, height, major):
        draw.rectangle(
            (0, y, width - 1, min(height - 1, y + major_width - 1)),
            fill=(255, 255, 255),
        )


def _draw_floor_grid(image: Any, image_draw: Any) -> None:
    width, height = image.size
    step = pattern_cell_size((width, height))
    line_width = _bounded_line_width(step, 3)
    draw = image_draw.Draw(image)
    for y_index, y in enumerate(range(0, height, step)):
        for x_index, x in enumerate(range(0, width, step)):
            fill = (105, 83, 51) if (x_index + y_index) % 2 else (132, 107, 66)
            draw.rectangle(
                (
                    x,
                    y,
                    min(width - 1, x + step - 1),
                    min(height - 1, y + step - 1),
                ),
                fill=fill,
            )
    for x in range(0, width, step):
        draw.rectangle(
            (x, 0, min(width - 1, x + line_width - 1), height - 1),
            fill=(255, 231, 151),
        )
    for y in range(0, height, step):
        draw.rectangle(
            (0, y, width - 1, min(height - 1, y + line_width - 1)),
            fill=(255, 231, 151),
        )


def _draw_position_pattern(image: Any, image_draw: Any) -> None:
    width, height = image.size
    draw = image_draw.Draw(image)
    for tile_y in range(POSITION_PATTERN_REPEATS):
        top = tile_y * height // POSITION_PATTERN_REPEATS
        bottom = (tile_y + 1) * height // POSITION_PATTERN_REPEATS - 1
        if bottom < top:
            continue
        half_height = top + (bottom - top + 1) // 2
        for tile_x in range(POSITION_PATTERN_REPEATS):
            left = tile_x * width // POSITION_PATTERN_REPEATS
            right = (tile_x + 1) * width // POSITION_PATTERN_REPEATS - 1
            if right < left:
                continue
            half_width = left + (right - left + 1) // 2
            draw.rectangle(
                (left, top, max(left, half_width - 1), max(top, half_height - 1)),
                fill=(239, 65, 65),
            )
            draw.rectangle(
                (half_width, top, right, max(top, half_height - 1)),
                fill=(62, 205, 119),
            )
            draw.rectangle(
                (left, half_height, max(left, half_width - 1), bottom),
                fill=(57, 104, 232),
            )
            draw.rectangle(
                (half_width, half_height, right, bottom),
                fill=(246, 210, 49),
            )
            draw.rectangle(
                (
                    max(left, half_width - 1),
                    top,
                    min(right, half_width + 1),
                    bottom,
                ),
                fill=(255, 255, 255),
            )
            draw.rectangle(
                (
                    left,
                    max(top, half_height - 1),
                    right,
                    min(bottom, half_height + 1),
                ),
                fill=(255, 255, 255),
            )


def _pattern_canvas(pattern: str, size: tuple[int, int], image: Any, image_draw: Any) -> Any:
    if pattern == "direction_checker":
        canvas = image.new("RGB", size, (0, 0, 0))
        _draw_direction_checker(canvas, image_draw)
        return canvas
    if pattern == "sky_grid":
        canvas = image.new("RGB", size, (67, 155, 231))
        _draw_sky_grid(canvas, image_draw)
        return canvas
    if pattern == "floor_grid":
        canvas = image.new("RGB", size, (132, 107, 66))
        _draw_floor_grid(canvas, image_draw)
        return canvas
    if pattern == "position_pattern":
        canvas = image.new("RGB", size, (0, 0, 0))
        _draw_position_pattern(canvas, image_draw)
        return canvas
    raise ScreenSpacePatternError(f"Unsupported screen-space pattern: {pattern}")


def _replace_frame(
    path: Path,
    *,
    expected_size: tuple[int, int],
    active_patterns: tuple[str, ...],
    pattern_ids: Mapping[str, tuple[int, int, int]],
    canvases: Mapping[str, Any],
    image: Any,
    image_chops: Any,
    unidentified_error: type[BaseException],
) -> dict[str, int]:
    if not path.is_file():
        raise ScreenSpacePatternError(f"Marker PNG does not exist: {path}")

    try:
        with image.open(path) as opened:
            if str(opened.format or "").upper() != "PNG":
                raise ScreenSpacePatternError(f"Marker frame is not a PNG: {path}")
            opened.load()
            if opened.size != expected_size:
                raise ScreenSpacePatternError(
                    f"Marker frame size mismatch for {path}: "
                    f"expected {expected_size[0]}x{expected_size[1]}, "
                    f"got {opened.size[0]}x{opened.size[1]}."
                )
            if opened.mode not in {"RGB", "RGBA"}:
                raise ScreenSpacePatternError(
                    f"Marker PNG must use RGB or RGBA pixels: {path} uses {opened.mode}."
                )
            source_rgb = opened.convert("RGB")
            output_rgb = source_rgb.copy()
            alpha = opened.getchannel("A").copy() if opened.mode == "RGBA" else None
    except ScreenSpacePatternError:
        raise
    except (unidentified_error, OSError, ValueError) as exc:
        raise ScreenSpacePatternError(f"Marker PNG is corrupt or unreadable: {path}") from exc

    counts: dict[str, int] = {}
    output: Any | None = None
    temporary: Path | None = None
    try:
        for pattern in active_patterns:
            mask = _exact_rgb_mask(source_rgb, pattern_ids[pattern], image_chops)
            try:
                count = int(mask.histogram()[255])
                counts[pattern] = count
                if count:
                    composited = image.composite(canvases[pattern], output_rgb, mask)
                    output_rgb.close()
                    output_rgb = composited
            finally:
                mask.close()

        total = sum(counts.values())
        if total <= 0:
            return counts

        output = output_rgb
        if alpha is not None:
            output = output_rgb.convert("RGBA")
            output.putalpha(alpha)

        temporary = path.with_name(
            f".{path.name}.{uuid.uuid4().hex}.hmb-screen-space.tmp.png"
        )
        output.save(temporary, format="PNG", compress_level=1)
        os.replace(temporary, path)
    except ScreenSpacePatternError:
        raise
    except Exception as exc:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
        raise ScreenSpacePatternError(
            f"Could not atomically publish screen-space marker PNG: {path}"
        ) from exc
    finally:
        if output is not None and output is not output_rgb:
            output.close()
        output_rgb.close()
        source_rgb.close()
        if alpha is not None:
            alpha.close()
    return counts


def postprocess_marker_frames(
    frame_paths: Iterable[os.PathLike[str] | str] | os.PathLike[str] | str,
    *,
    catalog: Mapping[str, Any],
    bindings: Iterable[Mapping[str, Any]] | None,
    expected_size: Sequence[int],
) -> dict[str, Any]:
    """Replace active categorical RGB pixels with fixed full-frame patterns."""

    size = _validated_size(expected_size)
    paths = _frame_paths(frame_paths)
    pattern_ids = validate_pattern_catalog(catalog)
    active_patterns = active_patterns_from_bindings(bindings, catalog)
    replaced_by_pattern = {name: 0 for name in active_patterns}
    report: dict[str, Any] = {
        "profile": PROFILE,
        "pattern_linear_scale_divisor": PATTERN_LINEAR_SCALE_DIVISOR,
        "pattern_cell_pixels": pattern_cell_size(size),
        "position_pattern_repeats": POSITION_PATTERN_REPEATS,
        "uv_dependent": False,
        "phase": PHASE,
        "origin": {"x": 0, "y": 0, "edge": "top_left"},
        "expected_size": {"width": size[0], "height": size[1]},
        "active_patterns": list(active_patterns),
        "frames_seen": len(paths),
        "frames_processed": 0,
        "frames_rewritten": 0,
        "replaced": {
            "total_pixels": 0,
            "by_pattern": replaced_by_pattern,
        },
        "no_op": not active_patterns,
    }
    if not active_patterns:
        return report

    image, image_chops, image_draw, unidentified_error, _version = _require_pillow()
    canvases = {
        pattern: _pattern_canvas(pattern, size, image, image_draw)
        for pattern in active_patterns
    }
    try:
        for path in paths:
            counts = _replace_frame(
                path,
                expected_size=size,
                active_patterns=active_patterns,
                pattern_ids=pattern_ids,
                canvases=canvases,
                image=image,
                image_chops=image_chops,
                unidentified_error=unidentified_error,
            )
            report["frames_processed"] += 1
            frame_total = sum(counts.values())
            if frame_total:
                report["frames_rewritten"] += 1
            report["replaced"]["total_pixels"] += frame_total
            for pattern, count in counts.items():
                replaced_by_pattern[pattern] += count
    finally:
        for canvas in canvases.values():
            canvas.close()
    return report
