"""Real installed-SDK serializer regression; private process, no engine or render.

Run with the supported SDK interpreter. No saved workflow is executed, and no
installed file is changed. Only this test process's native static method is
temporarily guarded and restored through the library's public lifecycle.
"""
from __future__ import annotations

import gc
import dataclasses
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import weakref

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
private = tempfile.TemporaryDirectory(prefix="hmb-save-identity-test-")
for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
        "XDG_STATE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR",
        "GTN_CONFIG_WORKSPACE_DIRECTORY"):
    value = Path(private.name) / key
    value.mkdir()
    os.environ[key] = str(value)

import _hmb_workflow_serialization_compat as target
from griptape_nodes.retained_mode.events.node_events import SerializedParameterValueTracker
from griptape_nodes.retained_mode.managers.node_manager import NodeManager
from griptape_nodes.serialization.values import encode_value
from griptape.artifacts.image_url_artifact import ImageUrlArtifact

class Owner:
    pass

class TrackedList(list):
    pass

original = NodeManager.__dict__[target._METHOD]
parameter = SimpleNamespace(serializable=True)
checks = []

def call(value, tracker, pool, name="parameter", supplied_parameter=parameter):
    return NodeManager._handle_value_hashing(value, tracker, pool,
        supplied_parameter, name, "Isolated serializer test", is_output=False)

def restored(command, pool):
    return pool[command.unique_value_uuid]

def check(label, condition):
    assert condition, label
    checks.append(label)

try:
    host = target._host()
    check("exact SDK method recognized", host is not None and target._known_descriptor(original, *host))
    # The unchecked native function must exhibit the concrete bug before the
    # fix is tested. The allocated IDs are real, never supplied by a mock.
    tracker = SerializedParameterValueTracker()
    pool = {}
    value = [{"image": "diagnostic-only"}]
    old_id = id(value)
    first = call(value, tracker, pool, "reference_images")
    del value
    value = []
    for _ in range(10000):
        if id(value) == old_id:
            break
        del value
        value = []
    check("native temporary-list identity reuse reproduced", id(value) == old_id)
    second = call(value, tracker, pool, "VIDEO_REFERENCES")
    check("native regression reproduced before correction", restored(second, pool) != [])
    del value, tracker, pool

    first_owner, second_owner = Owner(), Owner()
    check("first owner acquires", target.acquire(first_owner))
    check("duplicate acquire is idempotent", target.acquire(first_owner) and target.diagnostics()["owner_count"] == 1)
    guarded = NodeManager.__dict__[target._METHOD]
    check("descriptor remains staticmethod", type(guarded) is staticmethod)
    check("second owner acquires same wrapper", target.acquire(second_owner) and NodeManager.__dict__[target._METHOD] is guarded)

    tracker = SerializedParameterValueTracker()
    pool = {}
    image = ImageUrlArtifact("https://example.invalid/diagnostic-image.png")
    values = [[], {}, "", 0, False, [image], {"nested": [[], {}, "", 0, False]}]
    for i, value in enumerate(values):
        command = call(value, tracker, pool, str(i))
        check("native encoding preserved " + str(i), restored(command, pool) == encode_value(value))
    shared = [image]
    left = call(shared, tracker, pool, "shared_left")
    right = call(shared, tracker, pool, "shared_right")
    check("shared aliases preserve native pooled key", left.unique_value_uuid == right.unique_value_uuid)
    check("same-content distinct objects keep native deduplication",
        call([image], tracker, pool, "independent").unique_value_uuid == left.unique_value_uuid)

    value = TrackedList([image])
    live_value = weakref.ref(value)
    tracker_ref = weakref.ref(tracker)
    call(value, tracker, pool, "temporary_image_list")
    del value
    gc.collect()
    check("temporary value retained while save tracker lives", live_value() is not None)
    empty = call([], tracker, pool, "VIDEO_REFERENCES")
    check("empty video references never inherit image references", restored(empty, pool) == [])
    check("private references are not serialized tracker fields", target._VALUES_KEY not in dataclasses.asdict(tracker))
    del tracker
    gc.collect()
    check("tracker and temporary media released after save", tracker_ref() is None and live_value() is None)

    failure = RuntimeError("native serialization failure")
    class BrokenParameter:
        @property
        def serializable(self):
            raise failure
    tracker = SerializedParameterValueTracker()
    value = TrackedList(["failed save"])
    live_value, tracker_ref = weakref.ref(value), weakref.ref(tracker)
    try:
        call(value, tracker, {}, supplied_parameter=BrokenParameter())
    except RuntimeError as caught:
        check("native error is propagated unchanged", caught is failure)
    else:
        raise AssertionError("Native failure was suppressed")
    failure.__traceback__ = None
    del value, tracker
    gc.collect()
    check("failed save releases tracker and media", tracker_ref() is None and live_value() is None)

    # Importing the advanced library under another name/reloading it must not
    # add a second wrapper or lose the ownership of its first import.
    spec = importlib.util.spec_from_file_location("_hmb_save_guard_second_import", ROOT / "_hmb_workflow_serialization_compat.py")
    other = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(other)
    third_owner = Owner()
    check("second module import shares process-wide state", other.acquire(third_owner)
        and NodeManager.__dict__[target._METHOD] is guarded and other.diagnostics()["owner_count"] == 3)
    target.release(first_owner)
    target.release(second_owner)
    check("remaining owner keeps guard", NodeManager.__dict__[target._METHOD] is guarded)
    other.release(third_owner)
    check("last release restores exact native descriptor", NodeManager.__dict__[target._METHOD] is original)
    check("reacquire works after unload", target.acquire(first_owner)
        and NodeManager.__dict__[target._METHOD] is guarded)

    foreign = staticmethod(lambda *args, **kwargs: "foreign")
    NodeManager._handle_value_hashing = foreign
    check("foreign wrapper is never replaced by acquire", not other.acquire(second_owner)
        and NodeManager.__dict__[target._METHOD] is foreign)
    target.release(first_owner)
    check("foreign wrapper survives unload", NodeManager.__dict__[target._METHOD] is foreign)
    NodeManager._handle_value_hashing = original
    ephemeral_owner = Owner()
    check("owner can reacquire after foreign code restores native", target.acquire(ephemeral_owner))
    del ephemeral_owner
    gc.collect()
    check("weak owner collection restores native descriptor", NodeManager.__dict__[target._METHOD] is original)
    check("non-weak owner does not install partial guard", not target.acquire(object())
        and NodeManager.__dict__[target._METHOD] is original)
    check("foreign static function fails source recognition", not target._known_descriptor(foreign, *host))
    print(json.dumps({"passed": True, "checks": checks, "count": len(checks),
        "scope": "real SDK static serializer and library guard lifecycle; no live editor or render"}, ensure_ascii=False))
finally:
    NodeManager._handle_value_hashing = original
    for name in ("first_owner", "second_owner", "third_owner"):
        if name in globals():
            target.release(globals()[name])
    private.cleanup()
