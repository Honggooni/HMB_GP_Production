# -*- coding: utf-8 -*-
"""Strict default-layer capture and reversible legacy/Render Setup isolation.

Run without Maya for the guard/ambiguity contract. Optional --live-maya runs a
private three-render-layer .mb fixture through the actual installed Maya runner.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "resources/maya/HMB_Maya_Background_Preview.py"
maya_package = types.ModuleType("maya")
maya_cmds = types.ModuleType("maya.cmds")
maya_package.cmds = maya_cmds
sys.modules.setdefault("maya", maya_package)
sys.modules.setdefault("maya.cmds", maya_cmds)
spec = importlib.util.spec_from_file_location("hmb_capture_render_layer_runner", RUNNER_PATH)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class LayerCmds:
    def __init__(self, *, setup=False, ignore_default=False, fail_restore=False):
        self.current = "Original"
        self.setup = setup
        self.ignore_default = ignore_default
        self.fail_restore = fail_restore
        self.calls = []

    def editRenderLayerGlobals(self, query=False, currentRenderLayer=None):
        if query:
            return self.current
        self.calls.append(currentRenderLayer)
        if currentRenderLayer == "Original" and self.fail_restore:
            raise RuntimeError("synthetic legacy restoration failure")
        if currentRenderLayer != "defaultRenderLayer" or not self.ignore_default:
            self.current = currentRenderLayer

    def objExists(self, name):
        return name == "defaultRenderLayer"

    def nodeType(self, _name):
        return "renderLayer"

    def ls(self, type=None):
        return ["authoredSetupLayer"] if type == "renderSetupLayer" and self.setup else []


class SetupLayer:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class RenderSetup:
    def __init__(self, commands):
        self.commands = commands
        self.default = SetupLayer("defaultRenderLayer")
        self.authored = SetupLayer("authoredSetupLayer")
        self.visible = self.authored
        self.calls = []

    def getVisibleRenderLayer(self):
        return self.visible

    def getDefaultRenderLayer(self):
        return self.default

    def switchToLayer(self, layer):
        self.calls.append(layer.name())
        self.visible = layer
        self.commands.current = (
            "defaultRenderLayer" if layer is self.default else "Original"
        )


original_cmds = runner.cmds
for has_setup in (False, True):
    commands = LayerCmds(setup=has_setup)
    runner.cmds = commands
    modules = {}
    if has_setup:
        setup = RenderSetup(commands)
        for name in ("maya.app", "maya.app.renderSetup", "maya.app.renderSetup.model",
                     "maya.app.renderSetup.model.renderSetup"):
            modules[name] = sys.modules.get(name)
            sys.modules[name] = types.ModuleType(name)
        sys.modules["maya.app.renderSetup.model.renderSetup"].instance = lambda: setup
    try:
        context = runner._apply_capture_render_layer()
        assert commands.current == "defaultRenderLayer"
        assert context["report"]["default_layer_verified"] is True
        assert context["report"]["restored"] is False
        if has_setup:
            assert setup.visible is setup.default
            assert context["report"]["previous_render_setup_layer"] == "authoredSetupLayer"
        runner._restore_capture_render_layer(context)
        assert commands.current == "Original"
        assert context["report"]["restored"] is True
        assert context["report"]["restore_ok"] is True
        if has_setup:
            assert setup.visible is setup.authored
            assert setup.calls == ["defaultRenderLayer", "authoredSetupLayer"]
        calls = list(commands.calls)
        runner._restore_capture_render_layer(context)
        assert commands.calls == calls, "restoration must be idempotent"
    finally:
        for name, previous in modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

runner.cmds = LayerCmds(ignore_default=True)
try:
    runner._apply_capture_render_layer()
except RuntimeError as exc:
    assert "could not be isolated" in str(exc)
else:
    raise AssertionError("An ignored default-layer switch must stop capture.")
assert runner.cmds.current == "Original", "apply failure must restore authored layer"

runner.cmds = LayerCmds(fail_restore=True)
context = runner._apply_capture_render_layer()
try:
    runner._restore_capture_render_layer(context)
except RuntimeError as exc:
    assert "could not be restored" in str(exc)
else:
    raise AssertionError("A failed layer restoration must not publish success.")
assert context["report"]["restore_ok"] is False
runner.cmds = original_cmds

with tempfile.TemporaryDirectory(prefix="hmb_layer_output_") as temporary:
    folder = Path(temporary)
    prefix = "hmbvp_unique_frame"
    stamp = time.time()
    first = folder / (prefix + "_defaultRenderLayer.png")
    first.write_bytes(b"first")
    assert runner._rendered_file_for_unique_prefix(str(folder), prefix, stamp) == str(first)
    second = folder / (prefix + "_Original.png")
    second.write_bytes(b"second")
    try:
        runner._rendered_file_for_unique_prefix(str(folder), prefix, stamp)
    except RuntimeError as exc:
        assert "Ambiguous OGS output" in str(exc)
    else:
        raise AssertionError("Multiple authored-layer images must never choose the newest.")

source = RUNNER_PATH.read_text(encoding="utf-8")
run_source = source[source.index("def run(job_path):"):]
assert run_source.index("_apply_capture_render_layer()") < run_source.index("_read_job_bindings(job)")
assert run_source.index("_restore_capture_render_layer(capture_render_layer)") < run_source.index("payload = {")
assert '"layer": "defaultRenderLayer"' in source

NATIVE_WORKER = r'''from __future__ import annotations
import hashlib, importlib.util, json, os, traceback, uuid
from pathlib import Path
import maya.cmds as cmds
ROOT=Path("C:/HMB_GP_Production")
OUT=Path(os.environ["HMB_LAYER_TEST_OUTPUT"]).resolve()
OUT.mkdir(parents=True,exist_ok=True)
RUNNER=ROOT/"resources/maya/HMB_Maya_Background_Preview.py"
report={"ok":False,"roles":{},"scope":"Private three-layer binary fixture; no user scene touched."}
try:
    spec=importlib.util.spec_from_file_location("native_layer_runner",RUNNER)
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    source_before=hashlib.sha256(RUNNER.read_bytes()).hexdigest()
    cmds.optionVar(intValue=("renderSetupEnable", 0))
    cmds.file(new=True,force=True)
    cmds.currentUnit(time="film")
    cmds.playbackOptions(minTime=1,maxTime=1,animationStartTime=1,animationEndTime=1)
    hero=cmds.group(empty=True,name="HeroCharacter")
    body=cmds.polyCube(name="Body_GEO",width=2,height=2,depth=1)[0]
    cmds.parent(body,hero)
    camera,camera_shape=cmds.camera(name="LayerCamera",orthographic=True,orthographicWidth=5)
    camera=cmds.rename(camera,"LayerCamera")
    camera_shape=(cmds.listRelatives(camera,shapes=True,fullPath=True) or [])[0]
    cmds.setAttr(camera+".translateZ",10)
    cmds.setAttr(camera_shape+".renderable",True)
    cmds.setAttr("defaultResolution.width",640);cmds.setAttr("defaultResolution.height",360)
    cmds.setAttr("defaultResolution.deviceAspectRatio",640/360)
    def shader(name,rgb):
        node=cmds.shadingNode("surfaceShader",asShader=True,name=name)
        group=cmds.sets(renderable=True,noSurfaceShader=True,empty=True,name=name+"SG")
        cmds.connectAttr(node+".outColor",group+".surfaceShader",force=True)
        cmds.setAttr(node+".outColor",*rgb,type="double3")
        return group
    groups={name:shader("Authored"+name,rgb) for name,rgb in
            [("Default",(.1,.2,.8)),("Depth",(.4,.4,.4)),
             ("Mask",(.8,0,.8)),("Original",(0,.8,.1))]}
    cmds.sets(body,edit=True,forceElement=groups["Default"])
    for name in ("Original","Mask","Depth"):
        cmds.createRenderLayer(hero,name=name,makeCurrent=True)
        cmds.setAttr(name+".renderable",True)
        cmds.sets(body,edit=True,forceElement=groups[name])
    cmds.setAttr("defaultRenderLayer.renderable",False)
    cmds.editRenderLayerGlobals(currentRenderLayer="Original")
    scene=OUT/"AuthoredThreeRenderLayers.mb"
    cmds.file(rename=str(scene))
    cmds.file(save=True,type="mayaBinary",force=True)
    scene_before=hashlib.sha256(scene.read_bytes()).hexdigest()
    renderable_before={layer:int(cmds.getAttr(layer+".renderable")) for layer in cmds.ls(type="renderLayer")}
    raw=OUT/("baseline-all-renderable-"+uuid.uuid4().hex[:12]);raw.mkdir()
    cmds.workspace(fileRule=["images",str(raw).replace("\\","/")])
    cmds.setAttr("defaultRenderGlobals.imageFormat",32)
    cmds.setAttr("defaultRenderGlobals.imageFilePrefix","unisolated",type="string")
    runner._set_viewport_render_options(marker_mode=False,preserve_authored_look=True)
    cmds.ogsRender(camera=camera_shape,frame=1.0,width=640,height=360,noRenderView=True)
    baseline=list(raw.rglob("*.png"))
    assert len(baseline)>=3, [str(p) for p in baseline]
    report["baseline_images"]=[str(p) for p in baseline]
    report["baseline_image_count"]=len(baseline)
    newest=sorted(baseline,key=lambda p:(p.stat().st_mtime,str(p)))[-1]
    report["baseline_newest_image"]=str(newest)
    original_open_scene=runner._open_scene_for_job
    def authored_layer_callback(job):
        value=original_open_scene(job)
        # Maya loads this legacy fixture on its default layer. Simulate a real
        # scene-load callback restoring the authored visible Original layer;
        # capture must isolate it and restore that exact prior state afterward.
        cmds.editRenderLayerGlobals(currentRenderLayer="Original")
        return value
    runner._open_scene_for_job=authored_layer_callback
    for role in ("original","mask","depth"):
        folder=OUT/role;folder.mkdir(exist_ok=True)
        original=role=="original";depth=role=="depth"
        job={"operation":"snapshot","scene_path":str(scene),
             "result_path":str(folder/"result.json"),"progress_path":str(folder/"progress.json"),
             "frames_folder":str(folder/"frames"),"sidecar_path":str(folder/"color.hmb.json"),
             "output_name":role,"camera":"|LayerCamera","start_frame":1,"end_frame":1,"fps":24,
             "width":640,"height":360,"expected_maya_major":"2027","maya_evaluation_mode":"serial",
             "apply_marker_shaders":not original,"force_high_quality_viewport":True,
             "viewport_quality_profile":runner.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
             "require_full_smooth_geometry":True,"hidden_paths":[],
             "marker_catalog_path":str(ROOT/"resources/picker/HMB_Marker_Catalog.json"),
             "bindings":[] if original else [{"group_name":"HeroCharacter","subject_root":"|HeroCharacter","full_dag_path":"|HeroCharacter","color":"Red"}],
             "apply_original_lambert_override":original,
             "original_material_override_profile":runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE if original else "",
             "generate_depth_playblast":depth,"generate_motion_guide":False}
        if depth:
            job.update({"capture_pass":"depth","depth_frames_folder":str(folder/"depth-frames"),
                        "depth_output_name":"depth","depth_sidecar_path":str(folder/"depth.hmb.json"),
                        "depth_profile":runner.DEPTH_PLAYBLAST_PROFILE})
        job_path=folder/"job.json";job_path.write_text(json.dumps(job,indent=2),encoding="utf-8")
        result=runner.run(str(job_path))
        assert result["ok"] is True,result
        assert result["frame_count"]==1,result
        current=cmds.editRenderLayerGlobals(query=True,currentRenderLayer=True)
        assert current=="Original",current
        renderable_after={layer:int(cmds.getAttr(layer+".renderable")) for layer in cmds.ls(type="renderLayer")}
        assert renderable_before==renderable_after,(renderable_before,renderable_after)
        image=Path(result["frames_folder"])/(role+".000000.png")
        assert image.is_file(),image
        images=list(Path(result["frames_folder"]).rglob("*.png"))
        assert images==[image],images
        sidecar=json.loads(Path(result["sidecar_path"]).read_text(encoding="utf-8"))
        assert sidecar["capture_render_layer"]["restore_ok"] is True,sidecar
        report["roles"][role]={"image":str(image),"result":str(folder/"result.json"),
                               "sidecar":result["sidecar_path"],"report":result["capture_render_layer"],
                               "current_layer_after":current,"renderable_flags_preserved":True}
    report["scene_unchanged"]=hashlib.sha256(scene.read_bytes()).hexdigest()==scene_before
    report["runner_source_unchanged"]=hashlib.sha256(RUNNER.read_bytes()).hexdigest()==source_before
    assert report["scene_unchanged"] and report["runner_source_unchanged"]
    report["fixture"]=str(scene);report["fixture_sha256"]=scene_before
    report["ok"]=True
except Exception as exc:
    report["error"]=type(exc).__name__+": "+str(exc)
    report["traceback"]=traceback.format_exc()
    traceback.print_exc()
finally:
    (OUT/"native-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("HMB_LAYER_NATIVE_RESULT="+json.dumps({"ok":report["ok"],"error":report.get("error"),"report":str(OUT/"native-report.json")}),flush=True)
cmds.quit(force=True,exitCode=0 if report["ok"] else 1)
'''

parser = argparse.ArgumentParser()
parser.add_argument("--live-maya", action="store_true")
parser.add_argument("--output", type=Path, default=ROOT / ".test-cache/maya-layer-isolation-20261007")
args = parser.parse_args()
if args.live_maya:
    # The optional native companion is an ignored, generated script. This test
    # drives it in a hidden batch process, never an interactive/user Maya scene.
    sys.path.insert(0, str(ROOT))
    import HMBVideoPickerLibrary as picker
    args.output.mkdir(parents=True, exist_ok=True)
    worker = args.output / "native_layer_worker.py"
    worker.write_text(NATIVE_WORKER, encoding="utf-8")
    for name in ("maya-app", "tmp"):
        (args.output / name).mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment.update({"MAYA_APP_DIR": str(args.output / "maya-app"),
                        "TEMP": str(args.output / "tmp"), "TMP": str(args.output / "tmp"),
                        "HMB_LAYER_TEST_OUTPUT": str(args.output),
                        "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
                        "MAYA_DISABLE_CIP": "1", "MAYA_DISABLE_CER": "1",
                        "MAYA_DISABLE_ADP": "1",
                        "MAYA_ENABLE_LEGACY_RENDER_LAYERS": "1"})
    worker_path = str(worker).replace("\\", "/")
    command = 'python("import runpy;_hmb_layer_test_result=runpy.run_path(\'' + worker_path + "', run_name='__main__')\");"

    with (args.output / "mayabatch.log").open("w", encoding="utf-8", errors="replace") as log:
        process = subprocess.run([str(picker._find_mayabatch()), "-command", command],
                                 cwd=str(args.output), env=environment, stdout=log,
                                 stderr=subprocess.STDOUT, timeout=240,
                                 creationflags=picker._creation_flags(), check=False)
    assert process.returncode == 0, (args.output / "mayabatch.log").read_text(encoding="utf-8", errors="replace")[-8000:]
    result = json.loads((args.output / "native-report.json").read_text(encoding="utf-8"))
    assert result.get("ok") is True, result.get("error")
    from PIL import Image, ImageStat
    with Image.open(result["baseline_newest_image"]) as image:
        baseline_mean = ImageStat.Stat(image.convert("RGB").crop((255, 135, 385, 225))).mean
    assert baseline_mean[1] > baseline_mean[0] + 35 and baseline_mean[1] > baseline_mean[2] + 35, baseline_mean
    assert result["baseline_image_count"] == 3, result["baseline_images"]
    for role, record in result["roles"].items():
        with Image.open(record["image"]) as image:
            roi = image.convert("RGB").crop((255, 135, 385, 225))
            pixels = list(roi.get_flattened_data())
            mean = ImageStat.Stat(roi).mean
        if role in ("original", "depth"):
            assert max(max(p) - min(p) for p in pixels) <= 3, (role, mean)
        else:
            assert mean[0] > mean[1] + 35 and mean[0] > mean[2] + 35, (role, mean)
        assert record["report"]["capture_layer"] == "defaultRenderLayer"
        assert record["report"]["restore_ok"] is True
        assert record["current_layer_after"] == "Original"
    print("HMB_NATIVE_LAYER_REPORT=" + str(args.output / "native-report.json"))
print("PASS: strict default render layer, Render Setup visibility, failure restoration and ambiguous-output rejection.")
