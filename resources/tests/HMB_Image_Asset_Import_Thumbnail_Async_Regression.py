from __future__ import annotations

from io import BytesIO
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "hmb_image_asset_import_thumbnail_async", ROOT / "HMBImageAssetLibrary.py"
)
assert spec and spec.loader
library = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = library
spec.loader.exec_module(library)


def make_png(path: Path, color: tuple[int, int, int]) -> None:
    stream = BytesIO()
    Image.new("RGB", (13, 7), color).save(stream, format="PNG")
    path.write_bytes(stream.getvalue())


def live_imports(state):
    return [
        asset for asset in state["assets"]
        if asset["source_kind"] == "user" and asset["import_index"] > 0
    ]


with tempfile.TemporaryDirectory(prefix="hmb_import_preview_async_") as temp:
    # The runtime resolves imported paths. Windows CI may expose TEMP through
    # an 8.3 alias, so compare against the same canonical filesystem spelling.
    temp_root = Path(temp).resolve()
    path_a = temp_root / "A.png"
    path_b = temp_root / "B.png"
    make_png(path_a, (230, 30, 50))
    make_png(path_b, (20, 80, 190))
    node = library.HMBImageAssetLibrary(name="import_preview_async_regression")
    original_thumbnail = library._asset_thumbnail_url
    started_a = threading.Event()
    release_a = threading.Event()
    preview_threads = []

    def delayed_thumbnail(path, asset_id, _signature=""):
        preview_threads.append(threading.current_thread().name)
        if Path(path) == path_a:
            started_a.set()
            assert release_a.wait(5), "The controlled preview worker was not released."
        return f"https://example.invalid/workspace/static_files/{asset_id}.webp"

    library._asset_thumbnail_url = delayed_thumbnail
    try:
        # A path import is validated and available to IMAGE_OUT immediately;
        # only browser preview publication may wait for the decoder.
        published_a = node._apply_import_value([str(path_a)])
        first_worker = node._hmb_import_thumbnail_thread
        assert started_a.wait(5)
        first_row = live_imports(published_a)[0]
        assert first_row["path"] == path_a.as_posix()
        assert first_row["width"] == 13 and first_row["height"] == 7
        assert first_row["thumbnail_url"] == ""
        assert node.parameter_output_values[library.MEDIA_OUTPUT_PARAMETER] == [
            path_a.as_posix()
        ]
        first_uid = first_row["source_uid"]

        # A new connection snapshot supersedes the blocked preview. Its Shot
        # selection and output must win even if A finishes after B.
        published_b = node._apply_import_value([str(path_b)])
        second_row = live_imports(published_b)[0]
        assert second_row["source_uid"] != first_uid
        assert node.parameter_output_values[library.MEDIA_OUTPUT_PARAMETER] == [
            path_b.as_posix()
        ]
        asset_output_before_preview = node.parameter_output_values[
            library.OUTPUT_PARAMETER
        ]
        second_worker = node._hmb_import_thumbnail_thread
        second_worker.join(timeout=5)
        assert not second_worker.is_alive()
        original_publish_state = node._publish_state
        preview_publications = []

        def reentrant_publish(state, *args, **kwargs):
            preview_publications.append(1)
            assert node._consume_pending_import_thumbnail_result() is False, (
                "A host callback must not consume the same preview twice."
            )
            return original_publish_state(state, *args, **kwargs)

        node._publish_state = reentrant_publish
        try:
            assert node._consume_pending_import_thumbnail_result() is True
        finally:
            node._publish_state = original_publish_state
        assert len(preview_publications) == 1
        completed_b = node._current_state()
        assert [row["source_uid"] for row in live_imports(completed_b)] == [
            second_row["source_uid"]
        ]
        assert live_imports(completed_b)[0]["thumbnail_url"].endswith(
            f"{second_row['source_uid']}.webp"
        )
        assert node.parameter_output_values[library.MEDIA_OUTPUT_PARAMETER] == [
            path_b.as_posix()
        ]
        assert node.parameter_output_values[
            library.OUTPUT_PARAMETER
        ] == asset_output_before_preview
        assert completed_b["shot_routing"] == published_b["shot_routing"]

        release_a.set()
        first_worker.join(timeout=5)
        assert not first_worker.is_alive()
        assert node._consume_pending_import_thumbnail_result() is False
        assert live_imports(node._current_state()) == live_imports(completed_b)
        assert all(name.startswith("HMBImageImportPreview-") for name in preview_threads)

        # A disconnect retires every pending path preview without resurrecting
        # media or changing the empty output.
        cleared = node._apply_import_value([])
        assert live_imports(cleared) == []
        assert node.parameter_output_values[library.MEDIA_OUTPUT_PARAMETER] == []
        assert node._consume_pending_import_thumbnail_result() is False
    finally:
        release_a.set()
        library._asset_thumbnail_url = original_thumbnail

print("ImageAsset path preview async freshness/output regression: PASS")

with tempfile.TemporaryDirectory(prefix="hmb_import_preview_bounded_") as temp:
    temp_root = Path(temp).resolve()
    paths = {name: temp_root / f"{name}.png" for name in "ABCD"}
    for index, path in enumerate(paths.values()):
        make_png(path, (20 + index * 30, 50, 80))
    node = library.HMBImageAssetLibrary(name="import_preview_bounded_regression")
    original_thumbnail = library._asset_thumbnail_url
    entered = {name: threading.Event() for name in "ABCD"}
    release = {name: threading.Event() for name in "AB"}

    def held_thumbnail(path, asset_id, _signature=""):
        name = Path(path).stem
        entered[name].set()
        if name in release:
            assert release[name].wait(5), "The controlled decoder was not released."
        return f"https://example.invalid/workspace/static_files/{asset_id}.webp"

    library._asset_thumbnail_url = held_thumbnail
    try:
        node._apply_import_value([str(paths["A"])])
        thread_a = node._hmb_import_thumbnail_thread
        assert entered["A"].wait(5)
        node._apply_import_value([str(paths["B"])])
        thread_b = node._hmb_import_thumbnail_thread
        assert entered["B"].wait(5)
        node._apply_import_value([str(paths["C"])])
        node._apply_import_value([str(paths["D"])])
        assert node._hmb_import_thumbnail_active_workers == 2
        assert node._hmb_import_thumbnail_queued_task[0] == node._hmb_import_thumbnail_generation
        assert not entered["C"].is_set(), "Superseded queued work must not decode."
        release["B"].set()
        assert entered["D"].wait(5), "The latest queued preview must run when one slot opens."
        thread_b.join(timeout=5)
        assert not thread_b.is_alive()
        assert node._consume_pending_import_thumbnail_result() is True
        assert live_imports(node._current_state())[0]["path"] == paths["D"].as_posix()
        assert node._hmb_import_thumbnail_active_workers == 1
        release["A"].set()
        thread_a.join(timeout=5)
        assert not thread_a.is_alive()
        assert node._hmb_import_thumbnail_active_workers == 0
    finally:
        release["A"].set()
        release["B"].set()
        library._asset_thumbnail_url = original_thumbnail

print("ImageAsset bounded preview worker/latest-queue regression: PASS")
