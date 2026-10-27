"""Strict, side-effect-free fallback compositor for HMB Image Bash.

The installed editor exports around each image's centre: translate(x, y),
rotate(rotation), scale(scaleX, scaleY), drawImage(-width/2, -height/2).
Its Apply PNG is the authority for pixel-exact editor/Run output.  This PIL
renderer is the explicit metadata-recomposition path; browser and Pillow
interpolation can differ for fractional transforms.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from typing import Any

from PIL import Image, ImageColor


class ImageBashRenderError(ValueError):
    """The scene cannot be rendered completely and must not be published."""


def _number(value: Any, default: float, field: str) -> float:
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ImageBashRenderError(f"Invalid {field}.") from exc
    if not math.isfinite(result):
        raise ImageBashRenderError(f"Non-finite {field}.")
    return result


def _background(value: Any) -> tuple[int, int, int, int]:
    if isinstance(value, (tuple, list)) and len(value) in (3, 4):
        channels = tuple(value) + ((255,) if len(value) == 3 else ())
        if all(isinstance(channel, int) and 0 <= channel <= 255 for channel in channels):
            return channels
    if isinstance(value, str):
        if value.strip().lower() == "transparent":
            return (0, 0, 0, 0)
        rgba = re.fullmatch(
            r"\s*rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)\s*",
            value,
            flags=re.IGNORECASE,
        )
        if rgba:
            rgb = tuple(int(rgba.group(index)) for index in (1, 2, 3))
            alpha = _number(rgba.group(4), 1.0, "background alpha")
            if all(0 <= channel <= 255 for channel in rgb) and 0 <= alpha <= 1:
                return (*rgb, int(alpha * 255))
        try:
            return ImageColor.getcolor(value, "RGBA")
        except (TypeError, ValueError) as exc:
            raise ImageBashRenderError("Invalid background color.") from exc
    raise ImageBashRenderError("Invalid background color.")


def _scene_parts(scene: dict) -> tuple[Mapping, list]:
    if not isinstance(scene, dict):
        raise ImageBashRenderError("Scene must be a dictionary.")
    metadata = scene.get("meta", scene)
    if not isinstance(metadata, Mapping):
        raise ImageBashRenderError("Scene metadata must be a dictionary.")
    konva = metadata.get("konva_json", metadata)
    if not isinstance(konva, Mapping):
        raise ImageBashRenderError("Scene konva_json must be a dictionary.")
    if konva.get("lines"):
        raise ImageBashRenderError(
            "Raw vector lines require the editor's Apply render; apply the scene before Run."
        )
    layers = konva.get("images", [])
    if layers is None:
        layers = []
    if not isinstance(layers, list) or any(not isinstance(layer, Mapping) for layer in layers):
        raise ImageBashRenderError("Scene images must be a list of layer dictionaries.")
    return metadata, layers


def _sources(metadata: Mapping) -> dict[str, str]:
    records = metadata.get("input_images", [])
    if records is None:
        records = []
    if not isinstance(records, list):
        raise ImageBashRenderError("Scene input_images must be a list.")
    sources: dict[str, str] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ImageBashRenderError("Invalid source record.")
        source_id = record.get("id")
        url = record.get("url")
        if source_id is None:
            continue
        if not isinstance(source_id, str) or not source_id:
            raise ImageBashRenderError("Invalid source identity.")
        if not isinstance(url, str) or not url:
            raise ImageBashRenderError("Source record has no image URL.")
        if source_id in sources and sources[source_id] != url:
            raise ImageBashRenderError("A source identity resolves to different images.")
        sources[source_id] = url
    return sources


def _render_layer(
    canvas: Image.Image,
    layer: Mapping,
    sources: dict[str, str],
    load_image: Callable[[str], Image.Image],
) -> None:
    visible = layer.get("visible")
    if visible is not None and not isinstance(visible, bool):
        raise ImageBashRenderError("Layer visible must be a boolean.")
    if visible is False:
        return
    opacity = _number(layer.get("opacity"), 1.0, "layer opacity")
    if not 0 <= opacity <= 1:
        raise ImageBashRenderError("Layer opacity must be between 0 and 1.")
    scale_x = _number(layer.get("scaleX"), 1.0, "layer scaleX")
    scale_y = _number(layer.get("scaleY"), 1.0, "layer scaleY")
    if opacity == 0 or scale_x == 0 or scale_y == 0:
        return
    layer_type = layer.get("type") or "image"
    if layer_type not in ("image", "brush"):
        raise ImageBashRenderError(f"Unsupported layer type: {layer_type}.")
    if layer.get("globalCompositeOperation") not in (None, "source-over"):
        raise ImageBashRenderError("Unflattened blend operations require the editor's Apply render.")
    if _number(layer.get("skewX"), 0.0, "layer skewX") or _number(
        layer.get("skewY"), 0.0, "layer skewY"
    ):
        raise ImageBashRenderError("Skew transforms require the editor's Apply render.")

    source_id = layer.get("source_id")
    src = sources.get(source_id) if isinstance(source_id, str) else None
    # Apply persists brush rasters using their layer identity rather than source_id.
    if not src and layer_type == "brush" and isinstance(layer.get("id"), str):
        src = sources.get(layer["id"])
    if not src:
        src = layer.get("src")
    if not isinstance(src, str) or not src:
        raise ImageBashRenderError("A visible layer has no image source.")
    try:
        loaded = load_image(src)
        if not isinstance(loaded, Image.Image):
            raise TypeError("Image loader did not return a Pillow image.")
        loaded.load()
        image = loaded.convert("RGBA")
    except Exception as exc:
        # Never return an incomplete image or disclose source URL credentials.
        raise ImageBashRenderError("A required layer image could not be loaded.") from exc
    base_width = _number(layer.get("width"), float(image.width), "layer width")
    base_height = _number(layer.get("height"), float(image.height), "layer height")
    if base_width < 0 or base_height < 0:
        raise ImageBashRenderError("Layer dimensions cannot be negative; use scaleX/scaleY for flips.")
    if base_width == 0 or base_height == 0:
        return
    rotation = _number(layer.get("rotation"), 0.0, "layer rotation")
    x = _number(layer.get("x"), canvas.width / 2, "layer x")
    y = _number(layer.get("y"), canvas.height / 2, "layer y")
    angle = math.radians(rotation % 360)
    cos_angle, sin_angle = math.cos(angle), math.sin(angle)
    # Avoid one-pixel bounds noise around exact quarter-turns.
    if abs(cos_angle) < 1e-12:
        cos_angle = 0.0
    if abs(sin_angle) < 1e-12:
        sin_angle = 0.0
    corners = [
        (
            x + cos_angle * scale_x * u - sin_angle * scale_y * v,
            y + sin_angle * scale_x * u + cos_angle * scale_y * v,
        )
        for u in (-base_width / 2, base_width / 2)
        for v in (-base_height / 2, base_height / 2)
    ]
    left = max(0, math.floor(min(point[0] for point in corners)))
    top = max(0, math.floor(min(point[1] for point in corners)))
    right = min(canvas.width, math.ceil(max(point[0] for point in corners)))
    bottom = min(canvas.height, math.ceil(max(point[1] for point in corners)))
    if right <= left or bottom <= top:
        return
    if opacity < 1:
        image.putalpha(image.getchannel("A").point(lambda alpha: round(alpha * opacity)))

    # Invert T(x,y) * R * S * T(-width/2,-height/2), including signed scales.
    a = image.width / base_width * cos_angle / scale_x
    b = image.width / base_width * sin_angle / scale_x
    d = -image.height / base_height * sin_angle / scale_y
    e = image.height / base_height * cos_angle / scale_y
    c = image.width / 2 + a * (left - x) + b * (top - y)
    f = image.height / 2 + d * (left - x) + e * (top - y)
    transformed = image.transform(
        (right - left, bottom - top),
        Image.Transform.AFFINE,
        (a, b, c, d, e, f),
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )
    # Masked paste applies alpha twice. Use straight-alpha source-over instead.
    canvas.alpha_composite(transformed, (left, top))


def render_scene(
    scene: dict,
    width: int,
    height: int,
    background_color: Any = "#ffffff",
    load_image: Callable[[str], Image.Image] | None = None,
) -> Image.Image:
    """Render all visible raster layers or raise without publishing/writing anything.

    ``scene`` may be a full serialized bash_image, its meta dictionary, or a
    konva_json dictionary whose layers contain their own src URLs. Stable source
    identities resolve through meta.input_images; their list position has no
    effect. Duplicate layer instances remain independent and explicit order wins.
    Raw lines/blend/skew effects are rejected rather than silently discarded.
    """
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or width <= 0
        or height <= 0
    ):
        raise ImageBashRenderError("Canvas dimensions must be positive integers.")
    if load_image is None or not callable(load_image):
        raise ImageBashRenderError("An image loader is required.")
    metadata, layers = _scene_parts(scene)
    sources = _sources(metadata)
    indexed_layers = list(enumerate(layers))
    indexed_layers.sort(key=lambda pair: _number(pair[1].get("order"), pair[0], "layer order"))
    canvas = Image.new("RGBA", (width, height), _background(background_color))
    for _, layer in indexed_layers:
        _render_layer(canvas, layer, sources, load_image)
    return canvas
