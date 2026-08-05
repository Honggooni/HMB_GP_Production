from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "hmb_image_asset_disconnect_regression",
    ROOT / "HMBImageAssetLibrary.py",
)
assert SPEC is not None and SPEC.loader is not None
asset_library = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(asset_library)


def imported_uid(value: object) -> str:
    rows, _media = asset_library._normalize_import_input(value, [])
    assert len(rows) == 1
    return rows[0]["source_uid"]


class FakeNodeManager:
    def __init__(self, nodes: dict[str, object]):
        self.nodes = nodes

    def get_node_by_name(self, name: str) -> object:
        return self.nodes[name]


def connection(source: str, parameter: str = "IMAGE_OUT") -> SimpleNamespace:
    return SimpleNamespace(
        source_node_name=source,
        source_parameter_name=parameter,
        target_parameter_name=asset_library.IMAGE_IMPORT_PARAMETER,
    )


image_a = "https://example.test/disconnect-a.png"
image_b = "https://example.test/disconnect-b.png"
uid_a = imported_uid(image_a)
uid_b = imported_uid(image_b)
edge_a = connection("source_a")
edge_b = connection("source_b")
manager = FakeNodeManager(
    {
        "source_a": SimpleNamespace(parameter_output_values={"IMAGE_OUT": image_a}),
        "source_b": SimpleNamespace(parameter_output_values={"IMAGE_OUT": image_b}),
    }
)

assert asset_library._is_image_import_parameter(
    SimpleNamespace(name=asset_library.IMAGE_IMPORT_PARAMETER)
)
assert asset_library._is_image_import_parameter(
    SimpleNamespace(
        name="IMAGE_IMPORT_IN_ParameterListUniqueParamID_test",
        parent_container_name=asset_library.IMAGE_IMPORT_PARAMETER,
    )
)

assert asset_library._single_import_connection_for_uid(
    manager,
    [edge_a, edge_b],
    uid_a,
) is edge_a

compound_edge = connection("compound")
compound_manager = FakeNodeManager(
    {
        "compound": SimpleNamespace(
            parameter_output_values={"IMAGE_OUT": [image_a, image_b]}
        )
    }
)
try:
    asset_library._single_import_connection_for_uid(
        compound_manager,
        [compound_edge],
        uid_a,
    )
except RuntimeError as exc:
    assert "multiple images" in str(exc)
else:
    raise AssertionError("A multi-image edge must never be deleted from one card.")

duplicate_manager = FakeNodeManager(
    {
        "duplicate_a": SimpleNamespace(
            parameter_output_values={"IMAGE_OUT": image_a}
        ),
        "duplicate_b": SimpleNamespace(
            parameter_output_values={"IMAGE_OUT": image_a}
        ),
    }
)
try:
    asset_library._single_import_connection_for_uid(
        duplicate_manager,
        [connection("duplicate_a"), connection("duplicate_b")],
        uid_a,
    )
except RuntimeError as exc:
    assert "More than one" in str(exc)
else:
    raise AssertionError("Ambiguous duplicate edges must not be deleted.")

unresolved_manager = FakeNodeManager(
    {
        "source_a": manager.nodes["source_a"],
        "unreadable": SimpleNamespace(),
    }
)
try:
    asset_library._single_import_connection_for_uid(
        unresolved_manager,
        [edge_a, connection("unreadable")],
        uid_a,
    )
except RuntimeError as exc:
    assert "inspected safely" in str(exc)
else:
    raise AssertionError("Unreadable peer edges must block destructive matching.")

# A ParameterList snapshot is authoritative: removing A preserves B and drops
# only the stale external row.
state, _media = asset_library._merge_import_input(
    asset_library._default_state(),
    [image_a, image_b],
)
state, media = asset_library._merge_import_input(state, [image_b])
user_rows = [row for row in state["assets"] if row["source_kind"] == "user"]
assert [row["source_uid"] for row in user_rows] == [uid_b]
assert set(media) == {uid_b}

# The widget request removes a card only after the guarded graph operation
# succeeds.  A failure keeps both selection and media intact and reports it.
node = asset_library.HMBImageAssetLibrary(name="disconnect_request_success")
node._apply_import_value([image_a, image_b])
request_state = node._current_state()
request_state["disconnect_import_uid"] = uid_a
asset_library._set_parameter_value(
    node,
    asset_library.WIDGET_STATE_PARAMETER,
    json.dumps(request_state),
)
calls: list[str] = []
original_disconnect = asset_library._disconnect_import_connection
asset_library._disconnect_import_connection = lambda _node, uid: calls.append(uid)
try:
    successful = node._apply_widget_state(request_state)
finally:
    asset_library._disconnect_import_connection = original_disconnect
assert calls == [uid_a]
assert successful["disconnect_import_uid"] == ""
assert [
    row["source_uid"]
    for row in successful["assets"]
    if row["source_kind"] == "user"
] == [uid_b]
assert set(node._hmb_import_media_by_uid) == {uid_b}

failed_node = asset_library.HMBImageAssetLibrary(name="disconnect_request_failure")
failed_node._apply_import_value([image_a, image_b])
failed_request = failed_node._current_state()
failed_request["disconnect_import_uid"] = uid_a
asset_library._set_parameter_value(
    failed_node,
    asset_library.WIDGET_STATE_PARAMETER,
    json.dumps(failed_request),
)


def reject_disconnect(_node: object, _uid: str) -> None:
    raise RuntimeError("ambiguous test edge")


asset_library._disconnect_import_connection = reject_disconnect
try:
    failed = failed_node._apply_widget_state(failed_request)
finally:
    asset_library._disconnect_import_connection = original_disconnect
assert failed["disconnect_import_uid"] == ""
assert "ambiguous test edge" in failed["error"]
assert [
    row["source_uid"]
    for row in failed["assets"]
    if row["source_kind"] == "user"
] == [uid_a, uid_b]
assert set(failed_node._hmb_import_media_by_uid) == {uid_a, uid_b}


print("HMB ImageAsset guarded external disconnect regression: PASS")
