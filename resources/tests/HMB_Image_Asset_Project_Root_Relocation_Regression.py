"""Retired UNC root moves without changing Shot/asset identity or custom paths."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("image_root_relocation", ROOT / "HMBImageAssetLibrary.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
old = "//fin-rcomp1/Composite_Team/projects_AI"
new = "//192.168.200.19/v/projects/Ai_Ct_image"
for prefix in (old, old.upper(), old.replace("/", "\\")):
    for suffix in ("", "/superwings12", "/superwings12/캐릭터/Hero.png"):
        assert module._relocate_image_project_path(prefix + suffix) == new + suffix
        assert module._project_root_text({"path": prefix + suffix}) == new + suffix
for path in (old + "_archive/Hero.png", "//artist-server/custom-projects", r"D:\MyProject", "https://example.com/hero.png"):
    assert module._relocate_image_project_path(path) == path
assert module._project_root_text(Path(old + "/superwings12")) == new + "/superwings12"
assert module._project_root_text(json.dumps({"path": old})) == new
assert module._project_root_text("file://fin-rcomp1/Composite_Team/projects_AI/superwings12") == new + "/superwings12"

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
assert moved["project_root"] == moved["projects"][0]["path"] == new + "/superwings12"
assert moved["assets"][0]["path"] == new + "/superwings12/Character/Hero.png"
for field in ("asset_library_id", "source_uid", "asset_id", "selection_order", "selected"):
    assert moved["assets"][0][field] == raw["assets"][0][field]
assert moved["project_uid"] == raw["project_uid"]
assert moved["project_cache_uid"] == raw["project_cache_uid"]
assert moved["selected_folder_path"] == raw["selected_folder_path"]
assert module._normalize_state(moved) == moved
assert raw == original
already_moved = json.loads(json.dumps(raw).replace(old, new))
assert module._normalize_state(already_moved) == moved

# Defaults and stale environment overrides must resolve identically on startup.
for configured, expected in ((None, new), (old, new), ("//artist-server/custom-projects", "//artist-server/custom-projects")):
    env = dict(os.environ)
    env.pop("HMB_IMAGE_PROJECTS_ROOT", None)
    if configured is not None:
        env["HMB_IMAGE_PROJECTS_ROOT"] = configured
    code = "import HMBImageAssetLibrary as m; assert m._default_state()['catalog_root'].rstrip('/')==" + repr(expected)
    subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=env, check=True)
print("ImageAsset retired share relocation, native inputs, saved identity and custom paths: PASS")
