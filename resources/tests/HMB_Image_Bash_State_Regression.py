"""Stable asset ownership, lossless scene reconciliation and PNG receipts."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
import sys

from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from _hmb_image_bash_state import (
    ImageBashStateError, scene_fingerprint, sync_scene, validate_png_bytes,
)


def record(uid, url=None):
    return {"source_uid": uid, "url": url or f"file:///{uid}.png", "name": uid}


def factory(row, index):
    return {"id": f"canvas-img-{index+1}", "source_id": row["id"], "src": row["url"],
            "type": "image", "x": 100 + index, "y": 200, "opacity": 1,
            "scaleX": 1, "scaleY": 1, "rotation": 0, "order": index + 1}


def raises(call):
    try:
        call()
    except ImageBashStateError:
        return
    raise AssertionError("Expected ImageBashStateError")


original = {"value": "old.png", "name": "Canvas Project", "future_top": {"ok": True},
            "meta": {"viewport": {"x": -27, "y": 51, "scale": .44},
                     "future_meta": {"keep": [0, False, ""]},
                     "hmb_image_bash": {"apply_receipt": {"revision": "r1"}},
                     "konva_json": {"images": [], "lines": [{"points": [0, 1, 2, 3], "erase": True}],
                                    "future_scene": {"blend": "screen"}}}}
untouched = deepcopy(original)
first = sync_scene(original, [record("a"), record("b")], factory)
assert original == untouched
assert first["meta"]["viewport"] == original["meta"]["viewport"]
assert first["meta"]["future_meta"] == original["meta"]["future_meta"]
assert first["meta"]["konva_json"]["future_scene"] == {"blend": "screen"}
assert first["meta"]["hmb_image_bash"]["apply_receipt"] == {"revision": "r1"}
assert first["future_top"] == {"ok": True}
layers = first["meta"]["konva_json"]["images"]
layers[0].update(x=42, y=-71, scaleX=-2, opacity=0, visible=False,
                 future_transform={"skewX": .2})
duplicate = deepcopy(layers[0])
duplicate.update(id="dup-a", x=350, rotation=19, opacity=.6)
layers.insert(1, duplicate)
brush = {"id": "layer-brush", "source_id": "brush-1", "type": "brush", "src": "brush.png", "opacity": 0}
layers.insert(1, brush)
brush_input = {"id": "layer-brush", "url": "brush.png", "name": "Pen raster", "future_brush": [0, False]}
first["meta"]["input_images"].append(brush_input)
before_reorder = deepcopy(first)
reordered = sync_scene(first, [record("b"), record("a")], factory)
assert first == before_reorder
assert [row["source_uid"] for row in reordered["meta"]["input_images"] if "source_uid" in row] == ["b", "a"]
assert reordered["meta"]["input_images"][-1] == brush_input
assert reordered["meta"]["konva_json"] == before_reorder["meta"]["konva_json"]
assert len(reordered["meta"]["konva_json"]["images"]) == 4

# A library record can be repointed to new bytes without borrowing a neighbour's
# placement. Both duplicated occurrences update their source URL together.
changed = sync_scene(reordered, [record("b"), record("a", "file:///a-v2.png")], factory)
a_layers = [row for row in changed["meta"]["konva_json"]["images"] if row.get("source_uid") == "a"]
assert [(row["x"], row["src"]) for row in a_layers] == [(42, "file:///a-v2.png"), (350, "file:///a-v2.png")]
assert a_layers[0]["opacity"] == 0 and a_layers[0]["scaleX"] == -2
assert a_layers[0]["visible"] is False
assert a_layers[0]["future_transform"] == {"skewX": .2}
removed = sync_scene(changed, [record("b")], factory)
assert len(removed["meta"]["konva_json"]["images"]) == 2
assert removed["meta"]["konva_json"]["images"][0] == brush
assert removed["meta"]["konva_json"]["lines"] == original["meta"]["konva_json"]["lines"]
assert sync_scene(removed, [], factory)["meta"]["konva_json"]["images"] == [brush]
assert sync_scene(removed, [], factory)["meta"]["input_images"] == [brush_input]

# Deleting every occurrence in the editor is distinct from deselecting the
# external source. Apply must not recreate pixels absent from the exported PNG.
editor_deleted = deepcopy(first)
editor_deleted["meta"]["konva_json"]["images"] = [
    row for row in editor_deleted["meta"]["konva_json"]["images"] if row.get("source_uid") != "a"
]
editor_deleted["meta"]["input_images"] = [
    row for row in editor_deleted["meta"]["input_images"] if row.get("source_uid") != "a"
]
deleted_apply = sync_scene(editor_deleted, [record("a"), record("b")], factory, add_missing=False)
assert deleted_apply["meta"]["hmb_image_bash"]["suppressed_source_uids"] == ["a"]
assert {row.get("source_uid") for row in deleted_apply["meta"]["konva_json"]["images"]} == {None, "b"}
assert [row["source_uid"] for row in deleted_apply["meta"]["input_images"] if "source_uid" in row] == ["a", "b"]
resynced = sync_scene(deleted_apply, [record("a"), record("b")], factory)
assert resynced == deleted_apply
extra_selected = sync_scene(resynced, [record("a"), record("b"), record("c")], factory)
assert {row.get("source_uid") for row in extra_selected["meta"]["konva_json"]["images"]} == {None, "b", "c"}
deselected = sync_scene(extra_selected, [record("b"), record("c")], factory)
assert deselected["meta"]["hmb_image_bash"]["suppressed_source_uids"] == []
reselected = sync_scene(deselected, [record("a"), record("b"), record("c")], factory)
assert {row.get("source_uid") for row in reselected["meta"]["konva_json"]["images"]} == {None, "a", "b", "c"}

# Identical source bytes/URL are legal when ImageAsset gives distinct IDs.
same_url = [record("one", "file:///same.png"), record("two", "file:///same.png")]
same = sync_scene({}, same_url, factory)
assert len({row["id"] for row in same["meta"]["input_images"]}) == 2
same["meta"]["konva_json"]["images"][0]["x"] = 17
same_reordered = sync_scene(same, same_url[::-1], factory)
assert same_reordered["meta"]["konva_json"]["images"][0]["x"] == 17
assert same_reordered["meta"]["konva_json"]["images"][0]["source_uid"] == "one"
native_metadata_only = deepcopy(same)
native_metadata_only["meta"].pop("hmb_image_bash")
for row in native_metadata_only["meta"]["input_images"] + native_metadata_only["meta"]["konva_json"]["images"]:
    row.pop("source_uid", None)
restored_native = sync_scene(native_metadata_only, same_url[::-1], factory)
assert [row["source_uid"] for row in restored_native["meta"]["konva_json"]["images"]] == ["one", "two"]

legacy = {"meta": {"input_images": [{"id": "source-img-1", "url": "file:///a.png", "future_input": 42},
                                      {"id": "source-img-2", "url": "file:///b.png"}],
                    "konva_json": {"images": [{"id": "old-a", "type": "image", "source_id": "source-img-1", "x": 15},
                                               {"id": "old-a-copy", "type": "image", "source_id": "source-img-1", "x": 35},
                                               {"id": "old-b", "type": "image", "source_id": "source-img-2", "x": 99}],
                                   "lines": []}}}
migrated = sync_scene(legacy, [record("b"), record("a")], factory)
assert [(row["source_uid"], row["x"]) for row in migrated["meta"]["konva_json"]["images"]] == [("a", 15), ("a", 35), ("b", 99)]
assert migrated["meta"]["input_images"][1]["id"] == "source-img-1"
assert migrated["meta"]["input_images"][1]["future_input"] == 42
editor_duplicates = deepcopy(legacy)
editor_duplicates["meta"]["input_images"].append(deepcopy(editor_duplicates["meta"]["input_images"][0]))
assert sync_scene(editor_duplicates, [record("b"), record("a")], factory) == migrated
editor_duplicates["meta"]["input_images"][-1]["url"] = "file:///different.png"
raises(lambda: sync_scene(editor_duplicates, [record("b"), record("a")], factory))
editor_uid_conflict = deepcopy(migrated)
conflict_row = deepcopy(editor_uid_conflict["meta"]["input_images"][0])
conflict_row["source_uid"] = "different-asset"
editor_uid_conflict["meta"]["input_images"].append(conflict_row)
raises(lambda: sync_scene(editor_uid_conflict, [record("b"), record("a")], factory))
assert len(sync_scene(legacy, [record("b")], factory)["meta"]["konva_json"]["images"]) == 1
ambiguous = deepcopy(legacy)
ambiguous["meta"]["input_images"][1]["url"] = "file:///a.png"
raises(lambda: sync_scene(ambiguous, [record("a")], factory))
raises(lambda: sync_scene(legacy, [record("a"), record("copy", "file:///a.png")], factory))
raises(lambda: sync_scene({}, [record("a"), record("a")], factory))

# An editor duplication collision becomes a unique layer instance, not a lost
# occurrence. Image type prevents a layer-* image from being called a brush.
collision = deepcopy(migrated)
collision["meta"]["konva_json"]["images"][1]["id"] = "old-a"
fixed = sync_scene(collision, [record("a"), record("b")], factory)
assert len({row["id"] for row in fixed["meta"]["konva_json"]["images"]}) == 3
assert sync_scene(fixed, [record("a"), record("b")], factory) == fixed
layer_prefix_image = deepcopy(migrated)
layer_prefix_image["meta"]["konva_json"]["images"][0]["id"] = "layer-native-image"
assert not any(row["id"] == "layer-native-image" for row in sync_scene(layer_prefix_image, [record("b")], factory)["meta"]["konva_json"]["images"])

canvas = {"width": 64, "height": 32, "background_color": "#ffffff00"}
fingerprint = scene_fingerprint(first, [record("a"), record("b")], canvas)
bookkeeping = deepcopy(first)
bookkeeping["value"] = "new-apply.png"
bookkeeping["meta"]["viewport"]["scale"] = 12
bookkeeping["meta"]["hmb_image_bash"]["apply_receipt"] = {"revision": "r2"}
assert scene_fingerprint(bookkeeping, [record("a"), record("b")], canvas) == fingerprint
envelope = deepcopy(first)
envelope.update(id="sdk-artifact-instance", reference="sdk-runtime-reference")
assert scene_fingerprint(envelope, [record("a"), record("b")], canvas) == fingerprint
assert scene_fingerprint(first, [record("b"), record("a")], canvas) != fingerprint
assert scene_fingerprint(first, [record("a", "different.png"), record("b")], canvas) != fingerprint
different_brush = deepcopy(first)
different_brush["meta"]["konva_json"]["lines"][0]["points"][0] = 9
assert scene_fingerprint(different_brush, [record("a"), record("b")], canvas) != fingerprint
assert scene_fingerprint(first, [record("a"), record("b")], dict(canvas, width=65)) != fingerprint
assert scene_fingerprint(first, [dict(record("a"), media_signature="v2"), record("b")], canvas) == fingerprint
resolver_refresh = deepcopy(first)
for row in resolver_refresh["meta"]["input_images"]:
    row["media_signature"] = "new-cache-descriptor-with-identical-source-bytes"
assert scene_fingerprint(resolver_refresh, [record("a"), record("b")], canvas) == fingerprint
raises(lambda: scene_fingerprint(first, [record("a")], {"width": float("nan")}))

rgba = Image.new("RGBA", (7, 5), (10, 20, 30, 47))
png1, png2 = BytesIO(), BytesIO()
rgba.save(png1, format="PNG", compress_level=0)
info = PngImagePlugin.PngInfo()
info.add_text("description", "same pixels, distinct PNG")
rgba.save(png2, format="PNG", pnginfo=info, compress_level=9)
receipt1, receipt2 = validate_png_bytes(png1.getvalue()), validate_png_bytes(png2.getvalue())
assert (receipt1["width"], receipt1["height"]) == (7, 5)
assert receipt1["rgba_sha256"] == receipt2["rgba_sha256"]
assert receipt1["png_sha256"] != receipt2["png_sha256"]
raises(lambda: validate_png_bytes(png1.getvalue()[:-12]))
raises(lambda: validate_png_bytes(b"not PNG"))
raises(lambda: validate_png_bytes(png1.getvalue(), max_pixels=34))
print("HMB Image Bash state regression: PASS")
