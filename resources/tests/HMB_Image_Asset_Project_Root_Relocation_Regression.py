"""Retired UNC root moves without changing Shot/asset identity or custom paths."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("image_root_relocation", ROOT / "HMBImageAssetLibrary.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
old = "//fin-rcomp1/Composite_Team/projects_AI"
new = "//192.168.200.19/v/projects"
show = new + "/superwings12/Ai_Ct_image"
for prefix in (old, old.upper(), old.replace("/", "\\")):
    for suffix, expected in (("", new), ("/superwings12", show), ("/superwings12/캐릭터/Hero.png", show + "/캐릭터/Hero.png")):
        assert module._relocate_image_project_path(prefix + suffix) == expected
        assert module._project_root_text({"path": prefix + suffix}) == expected
for base in ("P:/projects", new):
    for suffix in ("", "/CH/Hero.png"):
        expected = base + "/superwings12/Ai_Ct_image" + suffix
        assert module._relocate_image_project_path(base + "/Ai_Ct_image/superwings12" + suffix) == expected
        assert module._relocate_image_project_path(base + "/superwings12/Ai_Ct_image/superwings12" + suffix) == expected
        assert module._relocate_image_project_path(expected) == expected
    assert module._relocate_image_project_path(base + "/Ai_Ct_image") == base
for path in (old + "_archive/Hero.png", "//artist-server/custom-projects", r"D:\MyProject", "https://example.com/hero.png"):
    assert module._relocate_image_project_path(path) == path
assert module._project_root_text(Path(old + "/superwings12")) == show
assert module._project_root_text(json.dumps({"path": old})) == new
assert module._project_root_text("file://fin-rcomp1/Composite_Team/projects_AI/superwings12") == show

raw = {"catalog_root": old, "project_root": old + "/superwings12", "project_id": "superwings12",
       "project_uid": "project-uid", "project_cache_uid": "cache-uid",
       "projects": [{"path": old + "/superwings12", "project_id": "superwings12", "project_uid": "project-uid", "name": "superwings12"}],
       "assets": [{"asset_library_id": "hero", "asset_id": "Hero", "image_name": "Hero", "source_uid": "project:hero",
                   "source_kind": "project", "registered": True, "selected": True, "selection_order": 1,
                   "path": old + "/superwings12/Character/Hero.png", "relative_path": "Character/Hero.png"}],
       "selected_folder_path": "Character", "folders": ["Character"], "expanded_folders": ["$root", "Character"]}
raw["shot_routing"] = module._default_state()["shot_routing"]
original = copy.deepcopy(raw)
moved = module._normalize_state(json.dumps(raw))
assert moved["catalog_root"] == new
assert moved["project_root"] == moved["projects"][0]["path"] == show
assert moved["assets"][0]["path"] == show + "/Character/Hero.png"
for field in ("asset_library_id", "source_uid", "asset_id", "selection_order", "selected"):
    assert moved["assets"][0][field] == raw["assets"][0][field]
assert moved["project_uid"] == raw["project_uid"]
assert moved["project_cache_uid"] == raw["project_cache_uid"]
assert moved["selected_folder_path"] == raw["selected_folder_path"]
assert module._normalize_state(moved) == moved
assert raw == original
already_moved = json.loads(json.dumps(raw).replace(old + "/superwings12", show).replace(old, new))
assert module._normalize_state(already_moved) == moved

# A saved CGT v2 forest owns independent native slots. Replacing only its
# retired address must not detach that forest, reissue IDs, or edit authority.
routing = module._hmb_shot_routing
def cgt_fixture(root):
    state = module._normalize_state({**raw, "project_root": root})
    account, pipeline = str(uuid4()), str(uuid4())
    members = []
    for index in range(1, 6):
        task = str(uuid4())
        name = f"e201s{index:03}c001__"
        members.append(dict(member_id="cgt:" + task, origin="cgt", manual_uuid=str(uuid4()),
            source_name=name, canonical_name=name,
            gp_shot_uuid=state["shot_routing"]["shots"][0]["shot_uuid"] if index == 1 else str(uuid4()),
            parent_id=None, selection_order=index, cgt_task_id=task, artist="Fixture Artist", status="InProgress",
            cgt_identity=dict(entity_id=str(uuid4()), task_id=task, pipeline_id=pipeline)))
    members[1]["parent_id"] = members[0]["member_id"]
    members[2]["parent_id"] = members[1]["member_id"]  # A child also owns its own group.
    members[4]["parent_id"] = members[3]["member_id"]
    binding = dict(schema=routing.SHOT_HIERARCHY_SCHEMA, version=2, binding_id=str(uuid4()), revision=1,
        project_identity=routing.hierarchy_project_key(state), channel_uuid=state["shot_routing"]["channel_uuid"],
        cgt_account_id=account, cgt_scope=dict(origin="https://cgt.fixture.invalid", project_id=str(uuid4()),
        project_db="fixture_sw12", module="shot", module_type="task", pipeline_id=pipeline, account_id=account), members=members)
    state = routing.apply_shot_hierarchy_edit(state, dict(schema=routing.SHOT_HIERARCHY_REQUEST_SCHEMA, version=1,
        expected_generation=state["shot_routing"]["generation"], expected_binding_revision=0, removed_member_ids=[], binding=binding))
    for shot in state["shot_routing"]["shots"]:
        shot["selected_source_uids"] = [state["assets"][0]["source_uid"]]
    return module._normalize_state(state)

hierarchy_cases = 0
for previous_root in (old + "/superwings12", new + "/Ai_Ct_image/superwings12",
                      "P:/projects/Ai_Ct_image/superwings12", new + "/superwings12/Ai_Ct_image/superwings12",
                      new + "/Ai_Ct_image/Katuri8"):
    canonical_root = module._relocate_image_project_path(previous_root)
    expected = cgt_fixture(canonical_root)
    expected_identity = routing.hierarchy_project_key(expected)
    for saved_root in (previous_root, canonical_root):  # Widget may canonicalize the root first.
        saved = copy.deepcopy(expected)
        saved["project_root"] = saved_root
        saved["shot_hierarchy"]["project_identity"] = previous_root.replace("\\", "/").lower()
        untouched = copy.deepcopy(saved)
        # These pure save/restore operations must perform no storage probes.
        with ExitStack() as stack:
            for method in ("stat", "lstat", "resolve", "iterdir", "open"):
                stack.enter_context(patch.object(Path, method, side_effect=AssertionError("Hierarchy migration performed IO")))
            stack.enter_context(patch.object(os, "scandir", side_effect=AssertionError("Hierarchy migration scanned storage")))
            restored = module._normalize_state(json.dumps(saved))
            assert restored["shot_hierarchy"] == expected["shot_hierarchy"]
            assert restored["shot_routing"] == expected["shot_routing"]
            assert restored["project_cache_uid"] == expected["project_cache_uid"]
            assert restored["project_uid"] == expected["project_uid"]
            assert module._normalize_state(json.dumps(restored)) == restored
            owner = SimpleNamespace(_current_state=lambda: restored)
            for shot in restored["shot_routing"]["shots"]:
                snapshot = module.HMBImageAssetLibrary._hmb_shot_hierarchy_snapshot(
                    owner, restored["shot_routing"]["channel_uuid"], shot["shot_uuid"])
                assert snapshot == expected["shot_hierarchy"]
            reconfirm = copy.deepcopy(restored["shot_hierarchy"])
            reconfirm["revision"] += 1
            assert routing.apply_shot_hierarchy_edit(restored, dict(schema=routing.SHOT_HIERARCHY_REQUEST_SCHEMA, version=1,
                expected_generation=restored["shot_routing"]["generation"], expected_binding_revision=restored["shot_hierarchy"]["revision"],
                removed_member_ids=[], binding=reconfirm)) == restored
        assert saved == untouched
        hierarchy_cases += 1
    for foreign_identity in (new + "/Ai_Ct_image/Other_Show", "D:/explicit/custom-project"):
        foreign = copy.deepcopy(expected)
        foreign["shot_hierarchy"]["project_identity"] = foreign_identity.lower()
        rejected = module._normalize_state(foreign)
        assert rejected["shot_hierarchy"] == foreign["shot_hierarchy"]
        owner = SimpleNamespace(_current_state=lambda: rejected)
        assert module.HMBImageAssetLibrary._hmb_shot_hierarchy_snapshot(owner,
            rejected["shot_routing"]["channel_uuid"], rejected["shot_routing"]["shots"][0]["shot_uuid"]) == {}
        hierarchy_cases += 1
print(f"ImageAsset CGT v2 hierarchy relocation/5-slot snapshots/reopen/no IO/foreign scope: PASS ({hierarchy_cases} cases)")

# Defaults and stale environment overrides must resolve identically on startup.
for configured, expected in ((None, new), (old, new), ("//artist-server/custom-projects", "//artist-server/custom-projects")):
    env = dict(os.environ)
    env.pop("HMB_IMAGE_PROJECTS_ROOT", None)
    if configured is not None:
        env["HMB_IMAGE_PROJECTS_ROOT"] = configured
    code = "import HMBImageAssetLibrary as m; assert m._default_state()['catalog_root'].rstrip('/')==" + repr(expected)
    subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=env, check=True)
print("ImageAsset retired share relocation, native inputs, saved identity and custom paths: PASS")
