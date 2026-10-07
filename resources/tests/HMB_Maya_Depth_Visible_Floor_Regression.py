"""Depth giant-floor regression, with optional private Maya binary/pixel proof."""
from __future__ import annotations
import argparse, hashlib, importlib.util, inspect, json, os, subprocess, sys, types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "resources/maya/HMB_Maya_Background_Preview.py"
maya = types.ModuleType("maya"); cmds_module = types.ModuleType("maya.cmds")
maya.cmds = cmds_module
sys.modules.setdefault("maya", maya); sys.modules.setdefault("maya.cmds", cmds_module)
spec = importlib.util.spec_from_file_location("floor_regression_runner", RUNNER)
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
assert runner.DEPTH_PLAYBLAST_PROFILE == "hmb_camera_space_depth_v8"
assert runner.DEPTH_VISIBLE_SURFACE_GRID_COLUMNS * runner.DEPTH_VISIBLE_SURFACE_GRID_ROWS == 35
class Point:
    def __init__(self, x,y,z,w=1): self.x,self.y,self.z=x,y,z
    def __mul__(self, _matrix): return self
class Geometry:
    bounds = [-10000, 0, -15000, 10000, 0, 5000]
    def exactWorldBoundingBox(self, _shape, **kwargs): return self.bounds
original_cmds, original_fallback = runner.cmds, runner._depth_visible_surface_fallback
runner.cmds = Geometry()
calls = []
runner._depth_visible_surface_fallback = lambda shape, matrix, om, depth, context: (calls.append(depth) or 12.0)
context = {"near":5.0,"far":90.0}
om = types.SimpleNamespace(MPoint=Point)
try:
    assert runner._depth_shape_representative_camera_depth("ground",None,om,frame=1) == 15000
    assert not calls, "The legacy default keeps bbox semantics unless correction context is present."
    assert runner._depth_shape_representative_camera_depth("ground",None,om,frame=1,visible_fallback=context) == 12
    assert calls == [15000]
    calls.clear()
    runner.cmds.bounds = [-1,-1,-40,1,1,-20]
    assert runner._depth_shape_representative_camera_depth("ordinary",None,om,visible_fallback=context) == 30
    assert not calls, "Objects already in range must avoid all camera-ray work."
    runner.cmds.bounds = [-1,-1,-2000,1,1,-1000]
    assert runner._depth_shape_representative_camera_depth("distant",None,om,visible_fallback=context) == 1500
    assert not calls, "A bbox wholly beyond the useful range has no nearer visible surface."
finally:
    runner.cmds,runner._depth_visible_surface_fallback=original_cmds,original_fallback
fallback_source = inspect.getsource(runner._depth_visible_surface_fallback)
assert "closestIntersection(" in fallback_source
assert "clip_near <= depth <= clip_far" in fallback_source
assert "0.0 < visible_depth < context" in fallback_source
assert 'if replaced:\n        report["records"].append' in fallback_source
assert "_depth_grayscale_bucket_index(" in inspect.getsource(runner._apply_depth_shader)
print("Depth giant-floor conditional camera-ray policy: PASS")

NATIVE_WORKER = r'''import hashlib,importlib.util,json,os,traceback
from pathlib import Path
import maya.cmds as cmds
ROOT=Path("C:/HMB_GP_Production")
OUT=Path(os.environ["HMB_FLOOR_TEST_OUTPUT"]).resolve()
RUNNER=ROOT/"resources/maya/HMB_Maya_Background_Preview.py"
report={"ok":False,"scope":"Private native binary giant-quad fixture; no user scene touched.","roles":{}}
try:
    spec=importlib.util.spec_from_file_location("native_floor_runner",RUNNER)
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    source_before=hashlib.sha256(RUNNER.read_bytes()).hexdigest()
    cmds.file(new=True,force=True);cmds.currentUnit(time="film")
    cmds.playbackOptions(minTime=1,maxTime=1,animationStartTime=1,animationEndTime=1)
    ground=cmds.polyPlane(name="GiantGround",width=20000,height=20000,subdivisionsX=1,subdivisionsY=1)[0]
    cmds.setAttr(ground+".translateZ",-4000)
    for index,depth in enumerate((15,30,50)):
        cube=cmds.polyCube(name="DepthObject"+str(index),width=3,height=3,depth=3)[0]
        cmds.setAttr(cube+".translate",(-1 if index%2 else 1)*4,1.5,-depth,type="double3")
    camera,shape=cmds.camera(name="FloorCamera")
    camera=cmds.rename(camera,"FloorCamera")
    shape=(cmds.listRelatives(camera,shapes=True,fullPath=True) or [])[0]
    cmds.setAttr(camera+".translate",0,4,10,type="double3")
    cmds.setAttr(camera+".rotateX",-15)
    cmds.setAttr(shape+".nearClipPlane",.1);cmds.setAttr(shape+".farClipPlane",10000)
    cmds.setAttr(shape+".renderable",True)
    cmds.setAttr("defaultResolution.width",640);cmds.setAttr("defaultResolution.height",360)
    cmds.setAttr("defaultResolution.deviceAspectRatio",640/360)
    scene=OUT/"GiantGround.mb";cmds.file(rename=str(scene));cmds.file(save=True,type="mayaBinary",force=True)
    scene_before=hashlib.sha256(scene.read_bytes()).hexdigest()
    real_fallback=runner._depth_visible_surface_fallback
    for role in ("baseline","fixed"):
        folder=OUT/role;folder.mkdir(exist_ok=True)
        runner._depth_visible_surface_fallback=(lambda shape,matrix,om,depth,context:depth) if role=="baseline" else real_fallback
        job={"operation":"snapshot","scene_path":str(scene),"result_path":str(folder/"result.json"),
             "progress_path":str(folder/"progress.json"),"frames_folder":str(folder/"color-unused"),
             "sidecar_path":str(folder/"color-unused.hmb.json"),"output_name":"unused",
             "depth_frames_folder":str(folder/"frames"),"depth_sidecar_path":str(folder/"depth.hmb.json"),
             "depth_output_name":"depth","capture_pass":"depth","camera":"|FloorCamera",
             "start_frame":1,"end_frame":1,"fps":24,"width":640,"height":360,
             "expected_maya_major":"2027","maya_evaluation_mode":"serial",
             "depth_near":5,"depth_far":90,"depth_profile":runner.DEPTH_PLAYBLAST_PROFILE,
             "apply_marker_shaders":True,"bindings":[],"hidden_paths":[],
             "generate_depth_playblast":True,"generate_motion_guide":False,"force_high_quality_viewport":True,
             "viewport_quality_profile":runner.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,
             "require_full_smooth_geometry":True,"marker_catalog_path":str(ROOT/"resources/picker/HMB_Marker_Catalog.json")}
        job_path=folder/"job.json";job_path.write_text(json.dumps(job,indent=2),encoding="utf-8")
        result=runner.run(str(job_path));assert result["ok"] is True,result
        sidecar=json.loads(Path(result["sidecar_path"]).read_text(encoding="utf-8"))
        image=Path(result["frames_folder"])/"depth.000000.png";assert image.is_file(),result
        report["roles"][role]={"png":str(image),"depth":sidecar["depth_range_report"],"capture_layer":result["capture_render_layer"]}
    corrected=report["roles"]["fixed"]["depth"]["visible_surface_fallback"]
    assert corrected["replaced_shape_frame_count"]>=1,corrected
    ground=[r for r in corrected["records"] if "GiantGround" in r["shape"]]
    assert len(ground)==1,corrected
    assert ground[0]["bbox_depth"]>=90 and 0<ground[0]["visible_depth"]<90,ground
    assert ground[0]["hit_count"]>0 and ground[0]["ray_test_count"]<=35,ground
    assert corrected["ray_test_count"]<=35*corrected["sampled_shape_frame_count"],corrected
    assert report["roles"]["fixed"]["capture_layer"]["restore_ok"] is True
    report["scene_unchanged"]=hashlib.sha256(scene.read_bytes()).hexdigest()==scene_before
    report["runner_source_unchanged"]=hashlib.sha256(RUNNER.read_bytes()).hexdigest()==source_before
    assert report["scene_unchanged"] and report["runner_source_unchanged"]
    report["ok"]=True
except Exception as exc:
    report["error"]=type(exc).__name__+": "+str(exc);report["traceback"]=traceback.format_exc();traceback.print_exc()
finally:
    (OUT/"native-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("HMB_FLOOR_NATIVE_RESULT="+json.dumps({"ok":report["ok"],"report":str(OUT/"native-report.json"),"error":report.get("error")}),flush=True)
cmds.quit(force=True,exitCode=0 if report["ok"] else 1)
'''
parser=argparse.ArgumentParser()
parser.add_argument("--live-maya",action="store_true")
parser.add_argument("--output",type=Path,default=ROOT/".test-cache/depth-visible-floor-20261007/native-giant-floor")
args=parser.parse_args()
if args.live_maya:
    args.output.mkdir(parents=True,exist_ok=True)
    worker=args.output/"native_worker.py";worker.write_text(NATIVE_WORKER,encoding="utf-8")
    for name in ("maya-app","tmp"): (args.output/name).mkdir(exist_ok=True)
    environment=os.environ.copy();environment.update({
        "MAYA_APP_DIR":str(args.output/"maya-app"),"TEMP":str(args.output/"tmp"),"TMP":str(args.output/"tmp"),
        "HMB_FLOOR_TEST_OUTPUT":str(args.output),"MAYA_ENABLE_LEGACY_RENDER_LAYERS":"1",
        "MAYA_DISABLE_CIP":"1","MAYA_DISABLE_CER":"1","MAYA_DISABLE_ADP":"1","PYTHONUTF8":"1"})
    worker_path=str(worker).replace("\\","/")
    command='python("import runpy;runpy.run_path(\\\''+worker_path+"\\',run_name=\\'__main__\\')\");"
    maya_path=os.environ.get("HMB_TEST_MAYABATCH","C:/Program Files/Autodesk/Maya2027/bin/mayabatch.exe")
    with (args.output/"mayabatch.log").open("w",encoding="utf-8",errors="replace") as log:
        process=subprocess.run([maya_path,"-command",command],cwd=str(args.output),env=environment,
                               stdout=log,stderr=subprocess.STDOUT,timeout=240,creationflags=0x08000000,check=False)
    assert process.returncode==0,(args.output/"mayabatch.log").read_text(encoding="utf-8",errors="replace")[-8000:]
    result=json.loads((args.output/"native-report.json").read_text(encoding="utf-8"))
    assert result["ok"],result
    from PIL import Image,ImageStat
    means={}
    for role in ("baseline","fixed"):
        with Image.open(result["roles"][role]["png"]) as image:
            region=image.convert("RGB").crop((240,260,400,320))
            pixels=list(region.get_flattened_data());mean=ImageStat.Stat(region).mean
            assert max(max(p)-min(p) for p in pixels)<=2,(role,mean)
            means[role]=mean
    assert max(means["baseline"])<=1,means
    assert min(means["fixed"])>35,means
    result["pixel_proof"]={"ground_roi":[240,260,400,320],"mean_rgb":means,"neutral":True}
    (args.output/"native-report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("Depth giant-floor binary Maya capture and actual neutral pixel correction: PASS")
