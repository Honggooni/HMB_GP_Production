from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "HMBVideoPickerLibrary.py"
SPEC = importlib.util.spec_from_file_location(
    "hmb_video_picker_server_media_reload_regression",
    TARGET,
)
assert SPEC is not None and SPEC.loader is not None
picker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = picker
SPEC.loader.exec_module(picker)


class FakeReadablePath:
    """Filesystem-free path double for a readable UNC video."""

    def __init__(self, value: str, mtime_ns: int = 1787558400000000000):
        self.value = value
        self.mtime_ns = mtime_ns

    def __str__(self) -> str:
        return self.value

    def resolve(self):
        return self

    def is_file(self) -> bool:
        return True

    def stat(self):
        return SimpleNamespace(st_mtime_ns=self.mtime_ns)


class FakeStaticFilesManager:
    static_server_base_url = "http://127.0.0.1:9777"


class FakeGriptapeNodes:
    @staticmethod
    def StaticFilesManager():
        return FakeStaticFilesManager()


module_names = (
    "griptape_nodes",
    "griptape_nodes.retained_mode",
    "griptape_nodes.retained_mode.griptape_nodes",
)
baseline_modules = {name: sys.modules.get(name) for name in module_names}
original_external_media_url = picker._external_media_url


def external_media_url_with_fake_server(path) -> str:
    """Inject only the static manager for the duration of one URL build."""

    saved_modules = {name: sys.modules.get(name) for name in module_names}
    package = ModuleType(module_names[0])
    package.__path__ = []
    retained = ModuleType(module_names[1])
    retained.__path__ = []
    leaf = ModuleType(module_names[2])
    leaf.GriptapeNodes = FakeGriptapeNodes
    previous_os_name = picker.os.name
    try:
        sys.modules[module_names[0]] = package
        sys.modules[module_names[1]] = retained
        sys.modules[module_names[2]] = leaf
        # Exercise the Windows-only UNC branch even in portable CI. The path
        # double prevents pathlib from touching a network or local filesystem.
        picker.os.name = "nt"
        return original_external_media_url(path)
    finally:
        picker.os.name = previous_os_name
        for name, saved in saved_modules.items():
            if saved is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved


def external_route_parameter(url: str) -> str:
    path = urlparse(url).path
    assert "/external/" in path
    return unquote(path.split("/external/", 1)[1])


server_scene = r"\\SERVER\Animation\show\shot_010\scene.ma"
server_color = r"\\SERVER\Animation\show\shot_010\scene\color.mp4"
server_original = r"\\SERVER\Animation\show\shot_010\scene\original.mp4"

try:
    # Maya LOAD accepts a lexical UNC scene without probing it in the retained
    # state parser. READ performs the later existence/permission check.
    assert picker._maya_scene_path_text(server_scene) == server_scene

    # Griptape 0.95.1 reconstructs the route parameter with Path(file_path).
    # The encoded value must therefore decode to a two-backslash UNC authority,
    # not a one-backslash current-drive rooted path.
    immediate_color_url = external_media_url_with_fake_server(
        FakeReadablePath(server_color)
    )
    decoded_color = external_route_parameter(immediate_color_url)
    assert decoded_color == server_color
    assert PureWindowsPath(decoded_color).is_absolute()
    assert PureWindowsPath(decoded_color).anchor == "\\\\SERVER\\Animation\\"
    assert "%5c%5cserver" in immediate_color_url.lower()

    with tempfile.TemporaryDirectory(prefix="hmb-picker-server-reload-") as temporary:
        project_copy = Path(temporary) / "project-color.mp4"
        project_copy.write_bytes(b"\x00\x00\x00\x18ftypmp42project-color")
        project_macro = "{inputs}/picker/project-color.mp4"

        state = picker._default_widget_state()
        state = picker._append_video_asset(
            state,
            {
                "video_uid": "server-color",
                "source_uid": "server-color",
                "label": "Server Color",
                "generation_role": "mask",
                "video_path": server_color,
                "project_video_path": project_macro,
                "video_url": "http://127.0.0.1:8124/external/stale-color.mp4",
            },
        )
        state.update(
            {
                "original_video_path": server_original,
                "original_video_url": (
                    "http://127.0.0.1:8124/external/stale-original.mp4"
                ),
                "original_preview_enabled": True,
            }
        )

        probes: list[str] = []
        original_resolver = picker._resolve_readable_video_reference
        original_request = picker._request_parameter_value
        picker._external_media_url = external_media_url_with_fake_server

        def resolve_without_network(value, **_kwargs):
            reference = str(value)
            probes.append(reference)
            if reference == project_macro:
                return project_copy
            if reference == server_original:
                return FakeReadablePath(server_original, 1787558400000000001)
            raise AssertionError(
                "Saved reload ignored the readable project copy and probed "
                f"an unnecessary server reference: {reference}"
            )

        picker._resolve_readable_video_reference = resolve_without_network
        picker._request_parameter_value = lambda *_args, **_kwargs: True
        # Bypass host registration while retaining the real bundled DataNode
        # class and the production hydration implementation. Constructing an
        # unregistered Griptape node would boot the whole desktop Engine and
        # make this filesystem contract depend on the user's global config.
        restored = object.__new__(picker.HMBVideoPickerLibrary)
        restored.name = "server_media_reload"
        restored.parameter_values = {}
        restored.metadata = {}
        restored._hmb_node_deleted = False
        restored._hmb_lifecycle_generation = 1
        restored._hmb_runtime_instance_id = "server-media-reload-runtime"
        restored._hmb_serialized_maya_scene_path = ""
        restored._hmb_state_revision = 0
        restored._hmb_authoritative_state = None
        restored._hmb_latest_widget_state = None
        restored._hmb_state_write_lock = threading.RLock()
        restored._hmb_state_sync_local = threading.local()
        restored.get_parameter_value = (
            lambda name: restored.parameter_values.get(name)
        )
        restored._store_initial_parameter_value(
            picker.WIDGET_STATE_PARAMETER,
            copy.deepcopy(state),
        )
        restored._ensure_parameters = lambda: None
        restored._sync_outputs_from_state = lambda _state: None
        try:
            restored._restore_dynamic_state(adopt_serialized=True)
        finally:
            picker._resolve_readable_video_reference = original_resolver
            picker._request_parameter_value = original_request
            picker._external_media_url = original_external_media_url

        hydrated = restored._picker_state()
        hydrated_video = next(
            item
            for item in hydrated["videos"]
            if item.get("video_uid") == "server-color"
        )
        assert probes == [project_macro, server_original]
        # Generated catalog media retains the project macro as its durable
        # authority and refreshes playback from the verified project copy.
        assert hydrated_video["project_video_path"] == project_macro
        assert project_copy.name in hydrated_video["video_url"]
        assert "stale-color" not in hydrated_video["video_url"]

        # Original Preview lives outside the card catalog until appended, so
        # its process-local URL must be refreshed independently on hydration.
        assert hydrated["original_preview_enabled"] is True
        assert "stale-original" not in hydrated["original_video_url"]
        decoded_original = external_route_parameter(
            hydrated["original_video_url"]
        )
        assert decoded_original == server_original
        assert PureWindowsPath(decoded_original).is_absolute()
finally:
    for name, saved in baseline_modules.items():
        if saved is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved


print("HMB VideoPicker server media URL + saved reload regression: PASS")
