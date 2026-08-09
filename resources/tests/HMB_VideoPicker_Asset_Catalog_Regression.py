from __future__ import annotations

from copy import deepcopy
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBVideoPickerLibrary.py"
SPEC = importlib.util.spec_from_file_location(
    "hmb_video_picker_asset_catalog_regression",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
picker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = picker
SPEC.loader.exec_module(picker)


def parameter_names(node) -> set[str]:
    parameters = getattr(node, "parameters", {})
    if isinstance(parameters, dict):
        return {str(name) for name in parameters}
    return {
        str(getattr(parameter, "name", ""))
        for parameter in parameters
        if getattr(parameter, "name", "")
    }


def parameter_by_name(node, name: str):
    getter = getattr(node, "get_parameter_by_name", None)
    if callable(getter):
        try:
            parameter = getter(name)
            if parameter is not None:
                return parameter
        except Exception:
            pass
    parameters = getattr(node, "parameters", {})
    if isinstance(parameters, dict):
        return parameters.get(name)
    return next(
        (
            parameter
            for parameter in parameters
            if str(getattr(parameter, "name", "")) == name
        ),
        None,
    )


def catalog_video(
    uid: str,
    order: int,
    *,
    selected: bool = True,
    role: str = "mask",
) -> dict:
    return {
        "video_uid": uid,
        "source_uid": uid,
        "video_path": f"C:/shot/catalog/{uid}.mp4",
        "label": uid,
        "generation_role": role,
        "media_kind": f"maya_{role}_playblast",
        "selected": selected,
        "selection_order": order if selected else 0,
        "source_fps": 24.0,
        "decoded_frame_count": 24,
        "start_frame": 101.0,
        "end_frame": 124.0,
        "has_maya_frame_range": True,
    }


# Picker has two and only two public media/metadata outputs. The generator gets
# one ordered list instead of ten independently wired and renumbered ports.
assert picker.MAX_SELECTED_VIDEOS == 10
assert picker.VIDEO_OUTPUT_PARAMETER == "VIDEO_OUT"
node = picker.HMBVideoPickerLibrary(name="Video Asset Catalog Contract")
names = parameter_names(node)
assert "PICKER_OUT" in names
assert "VIDEO_OUT" in names
for slot in range(1, 11):
    assert f"VIDEO{slot}_OUT" not in names
video_output_parameter = parameter_by_name(node, "VIDEO_OUT")
assert video_output_parameter is not None
declared_video_output_type = str(
    getattr(video_output_parameter, "output_type", "")
    or getattr(video_output_parameter, "type", "")
).replace(" ", "").lower()
assert declared_video_output_type in {
    "list[str]",
    "list[videourlartifact]",
    "list[videoartifact]",
}, declared_video_output_type
assert not any(
    f"VIDEO{slot}_OUT" in getattr(node, "parameter_output_values", {})
    for slot in range(1, 11)
)


# Catalog capacity and generator selection capacity are deliberately separate.
# All twelve records survive normalization, while only the first ten ordered
# records may be active in the Prompt/Generator snapshot.
source = picker._default_widget_state()
source["videos"] = [
    catalog_video(f"video-{index:02d}", index)
    for index in range(1, 13)
]
normalized = picker._parse_state(source)
assert len(normalized["videos"]) == 12
assert len({item["video_uid"] for item in normalized["videos"]}) == 12
assert all(item["source_uid"] == item["video_uid"] for item in normalized["videos"])
selected = [item for item in normalized["videos"] if item["selected"]]
assert len(selected) == 10
assert [item["selection_order"] for item in selected] == list(range(1, 11))
assert all(
    not item["selected"] and item["selection_order"] == 0
    for item in normalized["videos"][10:]
)

payload, media_values = picker._build_synchronized_video_outputs(normalized)
expected_uids = [f"video-{index:02d}" for index in range(1, 11)]
expected_paths = [f"C:/shot/catalog/{uid}.mp4" for uid in expected_uids]
assert [item["video_uid"] for item in payload["videos"]] == expected_uids
assert [item["source_uid"] for item in payload["videos"]] == expected_uids
assert [item["selection_order"] for item in payload["videos"]] == list(
    range(1, 11)
)
assert [item["video_slot"] for item in payload["videos"]] == list(range(1, 11))
assert media_values == expected_paths
assert len(payload["videos"]) == len(media_values) == 10
assert payload["selected_video_count"] == 10
assert payload["max_selected_videos"] == 10
assert payload["selection_id"]


# Reordering changes only the transient @video position. Stable identities,
# catalog membership, and the synchronized metadata/media snapshot stay paired.
reordered_source = deepcopy(normalized)
for item in reordered_source["videos"]:
    if item["selected"]:
        item["selection_order"] = 11 - int(item["selection_order"])
reordered = picker._parse_state(reordered_source)
reordered_payload, reordered_media = picker._build_synchronized_video_outputs(
    reordered
)
assert [item["video_uid"] for item in reordered_payload["videos"]] == list(
    reversed(expected_uids)
)
assert reordered_media == list(reversed(expected_paths))
assert [item["video_slot"] for item in reordered_payload["videos"]] == list(
    range(1, 11)
)
assert reordered_payload["selection_id"] != payload["selection_id"]
assert {
    item["video_uid"] for item in reordered["videos"]
} == {item["video_uid"] for item in normalized["videos"]}


# Reordering catalog assets is Prompt/Generator presentation only. Mask
# authoring remains permanently bound to the primary Maya assignment plane,
# and its bindings/visibility metadata must never follow card order.
authoring_source = picker._default_widget_state()
authoring_source.update({
    "mask_authoring_slot": 9,
    "videos": [
        catalog_video("authoring-a", 1),
        catalog_video("authoring-b", 2),
        catalog_video("authoring-c", 3),
    ],
    "slot_assignments": [
        {
            "video_slot": 1,
            "bindings": [{"maya_uuid": "hero-uuid", "color": "Red"}],
        },
        {
            "video_slot": 2,
            "bindings": [{"maya_uuid": "prop-uuid", "color": "Blue"}],
        },
    ],
    "slot_visibility": [
        {"video_slot": 1, "hidden_paths": ["|Hero|MouthCard"]},
        {"video_slot": 2, "hidden_paths": ["|Set|Proxy"]},
    ],
})
authoring_before = picker._parse_state(authoring_source)
assert picker._mask_authoring_slot(authoring_before) == 1
assignments_before = deepcopy(authoring_before["slot_assignments"])
visibility_before = deepcopy(authoring_before["slot_visibility"])
authoring_reorder_source = deepcopy(authoring_before)
for item in authoring_reorder_source["videos"]:
    item["selection_order"] = 4 - int(item["selection_order"])
authoring_after = picker._parse_state(authoring_reorder_source)
assert picker._mask_authoring_slot(authoring_after) == 1
assert authoring_after["slot_assignments"] == assignments_before
assert authoring_after["slot_visibility"] == visibility_before

# Both output ports are published from that same immutable selection snapshot;
# Prompt metadata cannot describe a different order than the generator list.
node._sync_outputs_from_state(
    reordered,
    enforce_media_availability=False,
)
published_values = getattr(node, "parameter_output_values", {})
assert published_values["VIDEO_OUT"] == reordered_media
published_picker = json.loads(published_values["PICKER_OUT"])
assert published_picker["selection_id"] == reordered_payload["selection_id"]
assert [item["video_uid"] for item in published_picker["videos"]] == [
    item["video_uid"] for item in reordered_payload["videos"]
]
assert [item["video_path"] for item in published_picker["videos"]] == (
    published_values["VIDEO_OUT"]
)


# Saved fixed-slot workflows migrate once into stable catalog identities. Their
# prior readable slot order becomes the initial selection order, not identity.
legacy = picker._parse_state({
    "active_slot_count": 4,
    "selected_video_slot": 4,
    "videos": [
        {
            "video_slot": 4,
            "video_path": "C:/legacy/motion.mp4",
            "generation_role": "motion_guide",
        },
        {
            "video_slot": 1,
            "video_path": "C:/legacy/original.mp4",
            "generation_role": "original",
        },
        {
            "video_slot": 2,
            "video_path": "C:/legacy/mask.mp4",
            "generation_role": "mask",
        },
    ],
})
legacy_selected = sorted(
    (item for item in legacy["videos"] if item["selected"]),
    key=lambda item: item["selection_order"],
)
assert [item["video_path"] for item in legacy_selected] == [
    "C:/legacy/original.mp4",
    "C:/legacy/mask.mp4",
    "C:/legacy/motion.mp4",
]
assert [item["selection_order"] for item in legacy_selected] == [1, 2, 3]
assert len({item["video_uid"] for item in legacy_selected}) == 3
assert all(item["source_uid"] == item["video_uid"] for item in legacy_selected)
legacy_uids = [item["video_uid"] for item in legacy_selected]
legacy_again = picker._parse_state(deepcopy(legacy))
assert [
    item["video_uid"]
    for item in sorted(
        (item for item in legacy_again["videos"] if item["selected"]),
        key=lambda item: item["selection_order"],
    )
] == legacy_uids
legacy_payload, legacy_media = picker._build_synchronized_video_outputs(legacy)
assert legacy_media == [
    "C:/legacy/original.mp4",
    "C:/legacy/mask.mp4",
    "C:/legacy/motion.mp4",
]
assert [item["video_uid"] for item in legacy_payload["videos"]] == legacy_uids


# Every generation appends a catalog record. Repeated roles and even a caller-
# supplied UID collision must mint a distinct identity rather than replace a
# previous take. The helper also leaves the caller's snapshot untouched.
append_base = picker._parse_state({
    "videos": [
        {
            **catalog_video("mask-take", 1, role="mask"),
            "video_path": "C:/shot/mask_take_001.mp4",
        }
    ]
})
append_base_before = deepcopy(append_base)
appended = picker._append_video_asset(
    append_base,
    {
        **catalog_video("mask-take", 2, role="mask"),
        "video_path": "C:/shot/mask_take_002.mp4",
    },
)
assert append_base == append_base_before
assert len(appended["videos"]) == 2
assert [item["video_path"] for item in appended["videos"]] == [
    "C:/shot/mask_take_001.mp4",
    "C:/shot/mask_take_002.mp4",
]
assert len({item["video_uid"] for item in appended["videos"]}) == 2
assert all(item["source_uid"] == item["video_uid"] for item in appended["videos"])

appended_again = picker._append_video_asset(
    appended,
    {
        "video_path": "C:/shot/mask_take_003.mp4",
        "generation_role": "mask",
        "media_kind": "maya_mask_playblast",
        "label": "Mask take 3",
    },
)
assert len(appended_again["videos"]) == 3
assert [item["video_path"] for item in appended_again["videos"]] == [
    "C:/shot/mask_take_001.mp4",
    "C:/shot/mask_take_002.mp4",
    "C:/shot/mask_take_003.mp4",
]
assert len({item["video_uid"] for item in appended_again["videos"]}) == 3


# MP4 import is an append-only catalog operation. With no Maya scene selected,
# it preserves the user's source as provenance while still publishing a browser-
# playable copy into the active Griptape project for every history record.
assert callable(picker._choose_video_asset_file)
assert callable(picker._choose_video_asset_files)
assert callable(getattr(picker.HMBVideoPickerLibrary, "_import_video_asset", None))
picker_source = MODULE_PATH.read_text(encoding="utf-8")
for command_name in (
    "browse_video_asset",
    "import_video_asset",
    "import_video_assets",
    "delete_video_asset",
):
    assert command_name in picker_source
chooser_source = inspect.getsource(picker._choose_video_asset_files)
assert "*.mp4" in chooser_source
assert "askopenfilenames" in chooser_source
assert "$d.Multiselect=$true" in chooser_source

tmp_parent = ROOT / ".tmp"
tmp_parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(
    prefix="hmb_video_asset_catalog_",
    dir=tmp_parent,
) as temporary:
    source_mp4 = Path(temporary) / "user_reference.mp4"
    # The Picker's structural validator requires complete top-level ftyp,
    # mdat, and moov boxes; payload decoding belongs to later media consumers.
    source_bytes = (
        b"\x00\x00\x00\x08ftyp"
        b"\x00\x00\x00\x08mdat"
        b"\x00\x00\x00\x08moov"
    )
    source_mp4.write_bytes(source_bytes)
    source_mp4_b = Path(temporary) / "user_reference_b.mp4"
    source_mp4_c = Path(temporary) / "user_reference_c.mp4"
    source_mp4_b.write_bytes(source_bytes)
    source_mp4_c.write_bytes(source_bytes)
    assert picker._is_structurally_valid_mp4(source_mp4)

    prior_test_selection = os.environ.get("HMB_VIDEO_ASSET_TEST_SELECTION")
    os.environ["HMB_VIDEO_ASSET_TEST_SELECTION"] = str(source_mp4)
    try:
        assert Path(picker._choose_video_asset_file()).resolve() == source_mp4.resolve()
    finally:
        if prior_test_selection is None:
            os.environ.pop("HMB_VIDEO_ASSET_TEST_SELECTION", None)
        else:
            os.environ["HMB_VIDEO_ASSET_TEST_SELECTION"] = prior_test_selection

    prior_test_selections = os.environ.get("HMB_VIDEO_ASSET_TEST_SELECTIONS")
    os.environ["HMB_VIDEO_ASSET_TEST_SELECTIONS"] = json.dumps([
        str(source_mp4_b),
        str(source_mp4_c),
    ])
    try:
        assert [
            Path(path).resolve()
            for path in picker._choose_video_asset_files()
        ] == [source_mp4_b.resolve(), source_mp4_c.resolve()]
        assert Path(picker._choose_video_asset_file()).resolve() == source_mp4_b.resolve()
    finally:
        if prior_test_selections is None:
            os.environ.pop("HMB_VIDEO_ASSET_TEST_SELECTIONS", None)
        else:
            os.environ["HMB_VIDEO_ASSET_TEST_SELECTIONS"] = prior_test_selections

    project_copies = []

    def copy_to_test_project(
        _node,
        path,
        _slot,
        *,
        transaction_records=None,
        backup_folder=None,
    ):
        assert transaction_records is not None
        assert backup_folder is not None
        target = Path(temporary) / f"project_copy_{len(project_copies) + 1}.mp4"
        target.write_bytes(Path(path).read_bytes())
        project_copies.append(target)
        return type("Artifact", (), {"meta": {"source": "test-project"}})(), str(target)

    original_project_copy = picker._copy_video_to_griptape_project
    picker._copy_video_to_griptape_project = copy_to_test_project
    try:
        imported_once = node._import_video_asset(
            picker._parse_state({"videos": []}),
            source_mp4,
            label="User Reference",
        )
        imported_twice = node._import_video_asset(
            imported_once,
            source_mp4,
            label="User Reference Take 2",
        )
    finally:
        picker._copy_video_to_griptape_project = original_project_copy
    imported_records = [
        item
        for item in imported_twice["videos"]
        if item.get("generation_role") == "imported"
    ]
    assert len(imported_records) == 2
    assert len({item["video_uid"] for item in imported_records}) == 2
    assert [item["label"] for item in imported_records] == [
        "User Reference",
        "User Reference Take 2",
    ]
    expected_source_path = str(source_mp4.resolve()).replace("\\", "/")
    assert all(
        item["video_path"] == expected_source_path
        and item["import_source_path"] == expected_source_path
        for item in imported_records
    )
    assert len(project_copies) == 2
    assert [Path(item["project_video_path"]).resolve() for item in imported_records] == [
        path.resolve() for path in project_copies
    ]
    assert all(
        project_copies[index].name in item["video_url"]
        for index, item in enumerate(imported_records)
    )
    assert source_mp4.read_bytes() == source_bytes

    # Exercise the real command branch while replacing only retained-mode
    # publication plumbing. Removing one history card must leave the source MP4
    # and every other UID untouched.
    command_state = {"value": deepcopy(imported_twice)}
    command_writes = []
    command_syncs = []
    node._picker_state = lambda: deepcopy(command_state["value"])
    def capture_command_write(value):
        command_writes.append(deepcopy(value))
        command_state["value"] = deepcopy(value)

    node._write_state = capture_command_write
    node._sync_outputs_from_state = lambda value: command_syncs.append(
        deepcopy(value)
    ) or ""
    picker._copy_video_to_griptape_project = copy_to_test_project
    try:
        node._handle_picker_command({
            "schema": picker.COMMAND_SCHEMA,
            "version": picker.COMMAND_VERSION,
            "runtime_instance_id": node._hmb_runtime_instance_id,
            "action": "import_video_assets",
            "action_id": "import-three-in-one-command",
            "payload": {
                "sources": [
                    {"source_path": str(source_mp4_b), "label": "Batch B"},
                    {"source_path": str(source_mp4_c), "label": "Batch C"},
                    {"source_path": str(source_mp4), "label": "Batch A Again"},
                ],
            },
        })
    finally:
        picker._copy_video_to_griptape_project = original_project_copy
    assert len(command_writes) == 1
    assert len(command_syncs) == 1
    assert [item["label"] for item in command_state["value"]["videos"][-3:]] == [
        "Batch B", "Batch C", "Batch A Again",
    ]
    assert len({
        item["video_uid"] for item in command_state["value"]["videos"][-3:]
    }) == 3

    command_writes.clear()
    command_syncs.clear()
    deleted_uid = imported_records[0]["video_uid"]
    retained_uid = imported_records[1]["video_uid"]
    node._handle_picker_command({
        "schema": picker.COMMAND_SCHEMA,
        "version": picker.COMMAND_VERSION,
        "runtime_instance_id": node._hmb_runtime_instance_id,
        "action": "delete_video_asset",
        "action_id": "delete-catalog-metadata-only",
        "payload": {"video_uid": deleted_uid},
    })
    after_delete = command_state["value"]
    after_delete_uids = {
        item["video_uid"] for item in after_delete["videos"]
    }
    assert deleted_uid not in after_delete_uids
    assert retained_uid in after_delete_uids
    assert source_mp4.read_bytes() == source_bytes


# Keep the non-destructive deletion guarantee visible in code review as well as
# behavior. Other Picker commands legitimately clean private caches, so inspect
# only the catalog-deletion branch rather than banning cleanup globally.
command_source = inspect.getsource(
    picker.HMBVideoPickerLibrary._handle_picker_command
)
delete_branch_start = command_source.index(
    'if action in {"delete_video_asset", "remove_video_asset", "delete_video"}'
)
delete_branch_end = command_source.index(
    'if action == "browse_maya_scene"',
    delete_branch_start,
)
delete_branch = command_source[delete_branch_start:delete_branch_end]
for destructive_token in (
    ".unlink(",
    "os.remove(",
    "shutil.rmtree(",
    "_safe_remove_private_tree(",
):
    assert destructive_token not in delete_branch


print(
    "HMB VideoPicker asset-catalog regression: PASS "
    "(two outputs, stable UID ordering, max-10 selection, migration, "
    "append/import-only, metadata-only delete)"
)
