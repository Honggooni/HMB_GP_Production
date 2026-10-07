"""Close Depth focus keeps compact subjects and nearby context, with private Maya proof."""
from __future__ import annotations
import argparse,importlib.util,json,os,subprocess,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
maya=types.ModuleType("maya");cmds=types.ModuleType("maya.cmds");maya.cmds=cmds
sys.modules.setdefault("maya",maya);sys.modules.setdefault("maya.cmds",cmds)
spec=importlib.util.spec_from_file_location("close_focus_test_runner",ROOT/"resources/maya/HMB_Maya_Background_Preview.py")
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
def records(root,depths,frame=1,role="foreground"):
    return [{"root":root,"frame":frame,"depth":d,"role":role,"normalization_eligible":True,"shape":root+str(i)} for i,d in enumerate(depths)]
rows=records("a",[15,16])+records("b",[16,17])+records("c",[18,19])+records("d",[17,18])+records("e",[.24,.26])+records("wide",[150,300,600,3100])
rows+=records("",[24.78,50,97],role="context")
focus=runner._depth_close_focus_range(rows,["a","b","c","d","e","wide"],.1,"close")
assert focus["applied"] and focus["chosen_roots"]==["a","b","c","d","e"],focus
assert focus["excluded_roots"]==["wide"] and focus["far"]==24.78,focus
assert focus["near"]==.1 and focus["local_context_sample_count"]==1,focus
assert focus["local_context_far"]<50,focus
# A distant compact subject is retained: distance alone never implies scenery.
far_compact=rows+records("far_actor",[100,100.001])
far_focus=runner._depth_close_focus_range(far_compact,["a","b","c","d","e","wide","far_actor"],.1,"close")
assert "far_actor" in far_focus["chosen_roots"],far_focus
# Compact spatial extent is independent of a complete-video trajectory.
animated=[]
for frame,depth in enumerate((20,200,500),1):
    animated+=records("moving",[depth,depth+.1],frame)
    for root,base in (("a",15),("b",16),("c",18)):
        animated+=records(root,[base,base+.1],frame)
    animated+=records("wide",[150,300,1000],frame)
animated_focus=runner._depth_close_focus_range(animated,["a","b","c","moving","wide"],.1,"close")
assert "moving" in animated_focus["chosen_roots"],animated_focus
moving=next(row for row in animated_focus["root_statistics"] if row["root"]=="moving")
assert abs(moving["spatial_span"]-.098)<1e-8 and moving["far_percentile"]>500, moving
for roots in ([],["a"],["a","b"]):
    assert runner._depth_close_focus_range(rows,roots,.1,"close")["applied"] is False
for mode in ("middle","far"):
    assert runner._depth_close_focus_range(rows,["a","b","c"],.1,mode)["applied"] is False
assert runner._depth_close_focus_range(rows,["a","b","c"],.1,"close",manual=True)["applied"] is False
ties=sum((records(root,[10,10]) for root in ("a","b","c")),[])
assert runner._depth_close_focus_range(ties,["a","b","c"],.1,"close")["chosen_roots"]==["a","b","c"]
tiny_rows=sum((records(root,[.102,.102]) for root in ("a","b","c")),[])
tiny=runner._depth_close_focus_range(tiny_rows,["a","b","c"],.1,"close",camera_far=.105)
assert tiny["applied"] and tiny["near"]==.1 and tiny["far"]==.105,tiny
assert tiny["local_context_far"]>.105, "Only the final physical far endpoint is clipped."
wide=runner._depth_close_focus_range(rows,["a","b","c","d","e","wide"],.1,"close",camera_far=10000)
assert wide==focus, "Ordinary clips retain the already-verified close focus exactly."
print("Depth close focus compact-root, local-context, weak-hint and temporal policy: PASS")

NATIVE=r'''import hashlib,importlib.util,json,os,traceback
from pathlib import Path
import maya.cmds as cmds
ROOT=Path("C:/HMB_GP_Production");OUT=Path(os.environ["HMB_CLOSE_TEST_OUTPUT"]).resolve()
RUNNER=ROOT/"resources/maya/HMB_Maya_Background_Preview.py"
report={"ok":False,"scope":"Private 3-frame binary scene and direct camera API checks; no user scene touched."}
try:
    spec=importlib.util.spec_from_file_location("native_close_runner",RUNNER)
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    source_before=hashlib.sha256(RUNNER.read_bytes()).hexdigest()
    cmds.file(new=True,force=True);cmds.currentUnit(time="film")
    cmds.playbackOptions(minTime=1,maxTime=3,animationStartTime=1,animationEndTime=3)
    roots=[]
    for i,z in enumerate((-5,-10,-15)):
        root=cmds.group(empty=True,name="CompactRoot"+str(i));roots.append(root)
        cube=cmds.polyCube(name="CompactShape"+str(i),width=2,height=2,depth=1)[0]
        cmds.parent(cube,root);cmds.setAttr(root+".translate",(i-1)*4,1.5,z,type="double3")
        if i==2:
            for frame,depth in ((1,-15),(2,-30),(3,-45)):
                cmds.setKeyframe(root,attribute="translateZ",time=frame,value=depth)
    wide=cmds.group(empty=True,name="WideRoot")
    for i,z in enumerate((-100,-300,-1000)):
        cube=cmds.polyCube(name="DistantContext"+str(i),width=10,height=20,depth=1)[0]
        cmds.parent(cube,wide);cmds.setAttr(cube+".translate",0,0,z,type="double3")
    floor=cmds.polyPlane(name="Ground",width=20000,height=20000,subdivisionsX=1,subdivisionsY=1)[0]
    cmds.setAttr(floor+".translateZ",-4000)
    camera,shape=cmds.camera(name="CloseCamera");camera=cmds.rename(camera,"CloseCamera")
    shape=cmds.listRelatives(camera,shapes=True,fullPath=True)[0]
    cmds.setAttr(camera+".translate",0,4,10,type="double3");cmds.setAttr(camera+".rotateX",-15)
    cmds.setAttr(shape+".nearClipPlane",.1);cmds.setAttr(shape+".farClipPlane",10000);cmds.setAttr(shape+".renderable",True)
    cmds.setAttr("defaultResolution.width",640);cmds.setAttr("defaultResolution.height",360);cmds.setAttr("defaultResolution.deviceAspectRatio",640/360)
    scene=OUT/"CloseFocus.mb";cmds.file(rename=str(scene));cmds.file(save=True,type="mayaBinary",force=True)
    before=hashlib.sha256(scene.read_bytes()).hexdigest()
    hints=[{"full_dag_path":"|"+root,"subject_root":"|"+root,"group_name":root,"color":color,"enabled":True} for root,color in zip(roots+[wide],["Red","Green","Blue","Cyan"])]
    job={"operation":"playblast","scene_path":str(scene),"result_path":str(OUT/"result.json"),"progress_path":str(OUT/"progress.json"),
         "frames_folder":str(OUT/"unused"),"sidecar_path":str(OUT/"unused.hmb.json"),"output_name":"unused",
         "depth_frames_folder":str(OUT/"frames"),"depth_sidecar_path":str(OUT/"depth.hmb.json"),"depth_output_name":"depth",
         "capture_pass":"depth","camera":"|CloseCamera","start_frame":1,"end_frame":3,"fps":24,"width":640,"height":360,
         "expected_maya_major":"2027","maya_evaluation_mode":"serial","depth_profile":runner.DEPTH_PLAYBLAST_PROFILE,
         "depth_range_mode":"close","depth_range_bindings":hints,"apply_marker_shaders":True,"bindings":[],"hidden_paths":[],
         "generate_depth_playblast":True,"generate_motion_guide":False,"force_high_quality_viewport":True,
         "viewport_quality_profile":runner.FULL_SMOOTH_VIEWPORT_QUALITY_PROFILE,"require_full_smooth_geometry":True,
         "marker_catalog_path":str(ROOT/"resources/picker/HMB_Marker_Catalog.json")}
    path=OUT/"job.json";path.write_text(json.dumps(job,indent=2),encoding="utf-8")
    result=runner.run(str(path));assert result["ok"] is True,result
    sidecar=json.loads(Path(result["sidecar_path"]).read_text(encoding="utf-8"))
    depth=sidecar["depth_range_report"];focus=depth["shot_range_sample"]["close_focus"]
    assert focus["applied"] is True and focus["excluded_roots"]==["|WideRoot"],focus
    assert len(focus["chosen_roots"])==3 and depth["near"]==.1,depth
    assert depth["range_evaluated_frame_count"]==3 and depth["assignment_verification"]["rendered_frame_count"]==3
    assert depth["temporal_normalization"]=="fixed_for_complete_sequence"
    assert sidecar["frame_count"]==3 and len(list((OUT/"frames").glob("*.png")))==3
    report["depth"]=depth;report["images"]=[str(p) for p in sorted((OUT/"frames").glob("*.png"))]
    report["scene_unchanged"]=hashlib.sha256(scene.read_bytes()).hexdigest()==before
    # Installed native camera API: wide ortho footprint and clipped-front mesh.
    cmds.file(new=True,force=True)
    ortho,ortho_shape=cmds.camera(orthographic=True,orthographicWidth=40)
    cmds.setAttr(ortho+".translateZ",10);cmds.setAttr(ortho_shape+".nearClipPlane",1);cmds.setAttr(ortho_shape+".farClipPlane",100)
    projection=runner._depth_camera_ray_projection(ortho,640,360)
    assert projection["is_ortho"] and abs((projection["right"]-projection["left"])-40)<1e-5,projection
    front=cmds.polyCreateFacet(point=[(-100,-100,9.5),(100,-100,9.5),(100,100,9.5),(-100,100,9.5)],name="BeforeNear")[0]
    back=cmds.polyCreateFacet(point=[(-100,-100,5),(100,-100,5),(100,100,5),(-100,100,5)],name="AfterNear")[0]
    combined=cmds.polyUnite(front,back,constructionHistory=False,name="ClippedCompound")[0]
    combined_shape=cmds.listRelatives(combined,shapes=True,fullPath=True)[0]
    om,matrix=runner._depth_camera_world_inverse_matrix(ortho)
    counters={"candidate_shape_frame_count":0,"sampled_shape_frame_count":0,"replaced_shape_frame_count":0,"unavailable_shape_frame_count":0,"ray_error_count":0,"ray_test_count":0,"hit_count":0,"records":[]}
    ctx={"camera":ortho,"width":640,"height":360,"near":1,"far":8,"frame":1,"report":counters}
    value=runner._depth_visible_surface_fallback(combined_shape,matrix,om,900,ctx)
    assert abs(value-5)<1e-5 and counters["hit_count"]==35 and counters["ray_error_count"]==0,(value,counters)
    report["orthographic_projection"]=projection;report["near_clip_compound_mesh"]=counters
    report["runner_source_unchanged"]=hashlib.sha256(RUNNER.read_bytes()).hexdigest()==source_before
    assert report["scene_unchanged"] and report["runner_source_unchanged"]
    report["ok"]=True
except Exception as exc:
    report["error"]=type(exc).__name__+": "+str(exc);report["traceback"]=traceback.format_exc();traceback.print_exc()
finally:
    (OUT/"native-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("HMB_CLOSE_NATIVE="+json.dumps({"ok":report["ok"],"error":report.get("error"),"report":str(OUT/"native-report.json")}),flush=True)
cmds.quit(force=True,exitCode=0 if report["ok"] else 1)
'''
parser=argparse.ArgumentParser();parser.add_argument("--live-maya",action="store_true")
parser.add_argument("--output",type=Path,default=ROOT/".test-cache/depth-visible-floor-20261007/native-close-focus")
args=parser.parse_args()
if args.live_maya:
    args.output.mkdir(parents=True,exist_ok=True)
    worker=args.output/"native_worker.py";worker.write_text(NATIVE,encoding="utf-8")
    for name in ("maya-app","tmp"): (args.output/name).mkdir(exist_ok=True)
    env=os.environ.copy();env.update({"MAYA_APP_DIR":str(args.output/"maya-app"),"TEMP":str(args.output/"tmp"),"TMP":str(args.output/"tmp"),
        "HMB_CLOSE_TEST_OUTPUT":str(args.output),"MAYA_ENABLE_LEGACY_RENDER_LAYERS":"1","MAYA_DISABLE_CIP":"1","MAYA_DISABLE_CER":"1","MAYA_DISABLE_ADP":"1","PYTHONUTF8":"1"})
    script=str(worker).replace("\\","/")
    command='python("import runpy;_close_result=runpy.run_path(\\\''+script+"\\',run_name=\\'__main__\\')\");"
    with (args.output/"mayabatch.log").open("w",encoding="utf-8",errors="replace") as log:
        process=subprocess.run([os.environ.get("HMB_TEST_MAYABATCH","C:/Program Files/Autodesk/Maya2027/bin/mayabatch.exe"),"-command",command],
            env=env,cwd=str(args.output),stdout=log,stderr=subprocess.STDOUT,timeout=240,creationflags=0x08000000)
    assert process.returncode==0,(args.output/"mayabatch.log").read_text(encoding="utf-8",errors="replace")[-8000:]
    proof=json.loads((args.output/"native-report.json").read_text(encoding="utf-8"));assert proof["ok"],proof
    from PIL import Image
    for image_path in proof["images"]:
        with Image.open(image_path) as image:
            pixels=list(image.convert("RGB").get_flattened_data())
            assert max(max(p)-min(p) for p in pixels)<=2
    print("Depth native 3-frame fixed close range, actual orthographic gate and behind-near hit: PASS")
