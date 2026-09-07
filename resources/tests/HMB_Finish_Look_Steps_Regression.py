"""Exercise the real JS stops against the Python state/compiler contract."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("finish_steps_target", ROOT / "HMBFinishLookLibrary.py")
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)
node = os.environ.get("HMB_NODE_EXE") or shutil.which("node")
if not node:
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
    if bundled.is_file():
        node = str(bundled)
assert node, "Node is required to validate the real widget step definitions"
script = """
import fs from 'node:fs';
const src = fs.readFileSync('widgets/HMBFinishLookLibraryWidget.js', 'utf8');
const widget = await import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'));
console.log(JSON.stringify(widget.HMB_FINISH_LOOK_STEPS));
"""
stops = json.loads(subprocess.check_output(
    [node, "--input-type=module", "-e", script], cwd=ROOT, text=True, encoding="utf-8"
))
assert len(stops) == 22
count = 0
for path, options in stops.items():
    group, field = path.split(".")
    prompts = set()
    for option in options:
        count += 1
        state = target.default_finish_look_state()
        # Glow threshold/width only take effect when glow is enabled.
        state["beauty"]["glow_brightness"] = 0.2
        state[group][field] = option["value"]
        normalized = target.validate_finish_look_state(state)
        assert normalized[group][field] == option["value"], (path, option)
        assert target.validate_finish_look_state(json.loads(json.dumps(state))) == normalized
        prompt = target.compile_finish_look_prompt(state)
        assert prompt not in prompts, ("Duplicate default-context step", path, option)
        prompts.add(prompt)
        assert "CHARACTER-MATTE-ONLY SCOPE" in prompt
        assert "FULL-FRAME SCOPE" in prompt
        disabled = copy.deepcopy(state)
        disabled[group]["enabled"] = False
        section = "CHARACTER BEAUTY —" if group == "beauty" else "FILTER APPLICATION —"
        assert section not in target.compile_finish_look_prompt(disabled)
print(f"Finish Look steps regression: PASS (22 controls, {count} stops, compiler/save/restore/disable)")
