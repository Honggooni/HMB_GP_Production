"""Lossless Image Bash scene reconciliation, independent of the node SDK.

An asset's ``source_uid`` belongs to the ImageAsset library. A Konva layer ID
belongs to an individual occurrence of that asset on the canvas. Neither is
derived from the input list position. This module never mutates its arguments.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid4, uuid5
import warnings


class ImageBashStateError(ValueError):
    """A scene cannot be reconciled or verified without losing its meaning."""


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _source_id(source_uid: str) -> str:
    return "hmb-src-" + uuid5(NAMESPACE_URL, "hmb-image-bash:" + source_uid).hex


def _is_brush(layer: dict) -> bool:
    # Explicit image type takes precedence: some editors use layer-* IDs for
    # duplicated image layers as well as rasterized brush layers.
    if layer.get("type") == "image":
        return False
    source = _text(layer.get("source_id")).lower()
    return (
        layer.get("type") == "brush"
        or "brush" in source
        or _text(layer.get("id")).startswith("layer-")
    )


def _records(records: list) -> list[dict]:
    if not isinstance(records, list):
        raise ImageBashStateError("ImageAsset records must be a list")
    result: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            raise ImageBashStateError(f"ImageAsset record {index + 1} must be an object")
        record = deepcopy(raw)
        uid, url = _text(record.get("source_uid")), _text(record.get("url"))
        if not uid.strip() or not url.strip():
            raise ImageBashStateError(f"ImageAsset record {index + 1} needs source_uid and url")
        if uid in seen:
            raise ImageBashStateError(f"Duplicate ImageAsset source_uid: {uid}")
        seen.add(uid)
        result.append(record)
    return result


def sync_scene(
    project: dict,
    records: list,
    create_layer: Callable[[dict, int], dict],
    *,
    add_missing: bool = True,
) -> dict:
    """Reconcile ImageAsset records into a full editor project, losslessly.

    ``create_layer`` receives a copied record with an additional native ``id``
    field and its zero-based current input index. It is called only for sources
    with no surviving canvas layer. Existing transforms, layer order, repeated
    occurrences, lines, viewport and unknown future fields are retained.

    Legacy projects without source_uid migrate only when a URL has exactly one
    old source and one current source. Ambiguous identical-URL selections fail
    before any data is changed. Removing a mapped source removes its image
    occurrences; brush layers and independent, unmapped scene objects remain.

    On editor Apply, pass ``add_missing=False``: absent source occurrences are
    intentional canvas deletions. Their identities remain suppressed during
    later input synchronization. Removing an asset from the library selection
    clears its suppression, so selecting it again creates a fresh layer.
    """
    if not isinstance(project, dict):
        raise ImageBashStateError("Image Bash project must be an object")
    result = deepcopy(project)
    current = _records(records)
    by_uid = {record["source_uid"]: record for record in current}
    current_url_counts = Counter(record["url"] for record in current)

    meta = result.setdefault("meta", {})
    if not isinstance(meta, dict):
        raise ImageBashStateError("Image Bash meta must be an object")
    hmb = meta.setdefault("hmb_image_bash", {})
    if not isinstance(hmb, dict):
        raise ImageBashStateError("Image Bash HMB metadata must be an object")
    stored_suppressed = hmb.get("suppressed_source_uids", [])
    if not isinstance(stored_suppressed, list) or any(not isinstance(uid, str) for uid in stored_suppressed):
        raise ImageBashStateError("Suppressed Image Bash sources must be a list of identities")
    suppressed = set(stored_suppressed) & set(by_uid)
    konva = meta.setdefault("konva_json", {"images": [], "lines": []})
    if not isinstance(konva, dict):
        raise ImageBashStateError("Image Bash konva_json must be an object")
    old_inputs = meta.get("input_images", [])
    old_layers = konva.get("images", [])
    if not isinstance(old_inputs, list) or any(not isinstance(row, dict) for row in old_inputs):
        raise ImageBashStateError("Image Bash input_images must contain objects")
    if not isinstance(old_layers, list) or any(not isinstance(row, dict) for row in old_layers):
        raise ImageBashStateError("Image Bash images must contain objects")

    # The actual editor serializes one input_images row per layer occurrence.
    # Duplicate layers therefore repeat a source ID. They are one source only
    # when the URL and any supplied stable identities agree.
    input_by_id: dict[str, dict] = {}
    unique_inputs: list[dict] = []
    for raw in old_inputs:
        sid = _text(raw.get("id"))
        if not sid:
            raise ImageBashStateError("Stored input image has no source ID")
        previous = input_by_id.get(sid)
        if previous is None:
            row = deepcopy(raw)
            input_by_id[sid] = row
            unique_inputs.append(row)
            continue
        old_uid, new_uid = _text(previous.get("source_uid")), _text(raw.get("source_uid"))
        if previous.get("url") != raw.get("url") or (old_uid and new_uid and old_uid != new_uid):
            raise ImageBashStateError("Repeated editor source ID has conflicting URL or asset identity")
        if new_uid and not old_uid:
            previous["source_uid"] = new_uid
        for key, value in raw.items():
            previous.setdefault(key, deepcopy(value))
    old_inputs = unique_inputs

    bindings = hmb.get("source_bindings", [])
    if not isinstance(bindings, list) or any(not isinstance(row, dict) for row in bindings):
        raise ImageBashStateError("Image Bash source_bindings must contain objects")
    sid_to_uid: dict[str, str] = {}
    uid_to_sid: dict[str, str] = {}
    old_row_by_uid: dict[str, dict] = {}

    def bind(uid: str, sid: str) -> None:
        if not uid or not sid:
            raise ImageBashStateError("Stored source binding has an empty identity")
        if sid in sid_to_uid and sid_to_uid[sid] != uid:
            raise ImageBashStateError("Stored source ID belongs to multiple assets")
        if uid in uid_to_sid and uid_to_sid[uid] != sid:
            raise ImageBashStateError("Stored asset belongs to multiple source IDs")
        sid_to_uid[sid] = uid
        uid_to_sid[uid] = sid

    for row in bindings:
        bind(_text(row.get("source_uid")), _text(row.get("source_id")))

    # The native editor may store rasterized brush assets in input_images as
    # well as in the scene. They belong to the project, not the external asset
    # channel, and must survive a source-list update or removal.
    brush_ids: set[str] = set()
    for layer in old_layers:
        if _is_brush(layer):
            brush_ids.update(value for value in (_text(layer.get("id")), _text(layer.get("source_id"))) if value)
    brush_input_rows: list[dict] = []

    # Old rows with stable identity are authoritative even if their URL changed.
    legacy: list[dict] = []
    old_source_ids: set[str] = set()
    deterministic_owners = {_source_id(uid): uid for uid in by_uid}
    for row in old_inputs:
        sid = _text(row.get("id"))
        if not sid:
            raise ImageBashStateError("Stored input image has no source ID")
        if sid in brush_ids or _is_brush(row) or sid.startswith("brush-"):
            brush_input_rows.append(deepcopy(row))
            continue
        old_source_ids.add(sid)
        uid = _text(row.get("source_uid")) or sid_to_uid.get(sid, "") or deterministic_owners.get(sid, "")
        if uid:
            bind(uid, sid)
            old_row_by_uid[uid] = row
        else:
            legacy.append(row)

    legacy_url_counts = Counter(_text(row.get("url")) for row in legacy)
    for row in legacy:
        url, sid = _text(row.get("url")), row["id"]
        matches = [record for record in current if record["url"] == url and record["source_uid"] not in uid_to_sid]
        if not matches:
            continue
        if legacy_url_counts[url] != 1 or current_url_counts[url] != 1 or len(matches) != 1:
            raise ImageBashStateError("Legacy identical-URL assets need explicit source_uid before migration")
        uid = matches[0]["source_uid"]
        bind(uid, sid)
        old_row_by_uid[uid] = row

    for record in current:
        uid = record["source_uid"]
        if uid not in uid_to_sid:
            bind(uid, _source_id(uid))

    active_sids = {uid_to_sid[uid]: uid for uid in by_uid}
    known_sids = old_source_ids | set(sid_to_uid)
    surviving: list[dict] = []
    represented: set[str] = set()

    for old_layer in old_layers:
        layer = deepcopy(old_layer)
        if _is_brush(layer):
            surviving.append(layer)
            continue
        sid = _text(layer.get("source_id"))
        uid = sid_to_uid.get(sid, "")
        layer_uid = _text(layer.get("source_uid"))
        if layer_uid:
            if uid and layer_uid != uid:
                raise ImageBashStateError("Layer identity disagrees with its source binding")
            uid = layer_uid
        if uid and uid not in by_uid:
            continue
        if not uid and sid in known_sids:
            # This is a removed legacy input with no current unambiguous match.
            continue
        if not uid and sid not in active_sids:
            # An old incomplete project may have the URL only on a layer.
            src = _text(layer.get("src"))
            matches = [record for record in current if record["url"] == src]
            if len(matches) > 1:
                raise ImageBashStateError("Unidentified image layer matches multiple ImageAsset sources")
            if len(matches) == 1:
                uid = matches[0]["source_uid"]
        if uid:
            record = by_uid[uid]
            layer["source_id"] = uid_to_sid[uid]
            layer["source_uid"] = uid
            layer["src"] = record["url"]
            represented.add(uid)
        surviving.append(layer)

    for index, record in enumerate(current):
        uid = record["source_uid"]
        if uid in represented:
            suppressed.discard(uid)
            continue
        if not add_missing:
            suppressed.add(uid)
            continue
        if uid in suppressed:
            continue
        native_record = deepcopy(record)
        native_record["id"] = uid_to_sid[uid]
        layer = create_layer(native_record, index)
        if not isinstance(layer, dict):
            raise ImageBashStateError("Image Bash layer factory must return an object")
        layer = deepcopy(layer)
        layer.update(source_id=uid_to_sid[uid], source_uid=uid, src=record["url"])
        surviving.append(layer)

    # Native duplication can emit an existing canvas-img ID. Layer IDs must be
    # unique, but source IDs deliberately repeat for repeated image occurrences.
    used_ids: set[str] = set()
    for layer in surviving:
        layer_id = _text(layer.get("id"))
        if not layer_id or layer_id in used_ids:
            layer_id = "hmb-layer-" + uuid4().hex
            layer["id"] = layer_id
        used_ids.add(layer_id)

    input_rows: list[dict] = []
    for record in current:
        uid = record["source_uid"]
        native_row = deepcopy(old_row_by_uid.get(uid, {}))
        native_row.update(deepcopy(record))
        native_row["id"] = uid_to_sid[uid]
        input_rows.append(native_row)
    meta["input_images"] = input_rows + brush_input_rows
    konva["images"] = surviving
    hmb["source_bindings"] = [
        {"source_uid": row["source_uid"], "source_id": row["id"], "url": row["url"]}
        for row in input_rows
    ]
    hmb["suppressed_source_uids"] = [row["source_uid"] for row in current if row["source_uid"] in suppressed]
    return result


def scene_fingerprint(project: dict, records: list, canvas: dict) -> str:
    """Hash scene/inputs/canvas, excluding exported pixels and view bookkeeping.

    The full raw Konva scene is included, including future fields and brush
    strokes. HMB transaction receipts and viewport pan/zoom do not alter pixels
    and are excluded so recording an Apply receipt does not invalidate itself.
    """
    if not isinstance(project, dict) or not isinstance(canvas, dict):
        raise ImageBashStateError("Fingerprint needs project and canvas objects")
    scene = deepcopy(project)
    scene.pop("value", None)
    # Native Run materializes the JsonArtifact envelope and adds these keys.
    # They identify the SDK object, not the canvas or any source/layer identity.
    scene.pop("id", None)
    scene.pop("reference", None)
    meta = scene.get("meta", {})
    if not isinstance(meta, dict):
        raise ImageBashStateError("Image Bash meta must be an object")
    meta.pop("viewport", None)
    meta.pop("hmb_image_bash", None)
    # ImageAsset's optional resolver/cache signature can change when a native
    # Run refreshes imports, without changing any source byte. Source freshness
    # is proved separately by the receipt's actual byte/RGBA hashes.
    for row in meta.get("input_images", []):
        if isinstance(row, dict):
            row.pop("media_signature", None)
    authored_records = _records(records)
    for row in authored_records:
        row.pop("media_signature", None)
    try:
        canonical = json.dumps(
            {"project": scene, "records": authored_records, "canvas": canvas},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ImageBashStateError("Image Bash scene must be finite JSON data") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_png_bytes(data: bytes, *, max_pixels: int = 100_000_000) -> dict:
    """Fully decode a single PNG and return dimensions and byte/pixel hashes."""
    from PIL import Image

    if not isinstance(data, bytes) or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ImageBashStateError("Apply output must be PNG bytes")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=("PNG",)) as image:
                width, height = image.size
                if width < 1 or height < 1 or width * height > max_pixels:
                    raise ImageBashStateError("Apply PNG dimensions exceed the supported canvas")
                if getattr(image, "n_frames", 1) != 1:
                    raise ImageBashStateError("Apply output must be one raster canvas")
                image.verify()
            with Image.open(BytesIO(data), formats=("PNG",)) as image:
                rgba = image.convert("RGBA")
                rgba.load()
                pixels = rgba.tobytes()
    except ImageBashStateError:
        raise
    except Exception as exc:
        raise ImageBashStateError("Apply PNG is corrupt or cannot be decoded") from exc
    return {
        "width": width, "height": height,
        "rgba_sha256": hashlib.sha256(pixels).hexdigest(),
        "png_sha256": hashlib.sha256(data).hexdigest(),
    }
