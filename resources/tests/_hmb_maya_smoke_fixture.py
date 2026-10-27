"""Build the private, deterministic scene used by the three native smoke tests.

The fixture has one animated mesh/joint actor and one separate prop. It has no
face controls or external references. Run this helper with mayapy and a new
.ma path under this checkout's .tmp or reports directory; existing files are
never replaced. Importing the helper in ordinary Python does not import Maya.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def isolated_maya_environment(run_folder: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    """Retain vendor login discovery while separating test settings and caches."""
    environment = dict(os.environ if base is None else base)
    folders = {
        "MAYA_APP_DIR": run_folder / "maya-profile",
        "LOCALAPPDATA": run_folder / "local-app-data",
        "TEMP": run_folder / "native-temp",
    }
    for name, folder in folders.items():
        folder.mkdir(parents=True, exist_ok=True)
        environment[name] = str(folder.resolve())
    environment.update(TMP=environment["TEMP"], TMPDIR=environment["TEMP"],
        PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
        MAYA_DISABLE_CIP="1", MAYA_DISABLE_CER="1", MAYA_DISABLE_ADP="1")
    if os.name == "nt" and not environment.get("MAYA_VP2_DEVICE_OVERRIDE"):
        environment["MAYA_VP2_DEVICE_OVERRIDE"] = "VirtualDeviceDx11"
    return environment


def build_scene(destination: Path) -> None:
    destination = destination.resolve()
    if destination.suffix.lower() != ".ma" or not any(
        destination.is_relative_to(ROOT / folder) for folder in (".tmp", "reports")
    ):
        raise ValueError("A private checkout .tmp/reports .ma destination is required")
    if destination.exists():
        raise FileExistsError("Native smoke fixture never overwrites an existing scene")
    destination.parent.mkdir(parents=True, exist_ok=True)

    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        import maya.cmds as cmds
        cmds.file(new=True, force=True)
        cmds.currentUnit(time="film", linear="cm", angle="deg")
        cmds.playbackOptions(minTime=1, maxTime=3, animationStartTime=1, animationEndTime=3)

        actor = cmds.group(empty=True, name="MotionActor_G")
        mesh = cmds.polySphere(name="MotionActorMesh", radius=1, subdivisionsX=20, subdivisionsY=12)[0]
        cmds.parent(mesh, actor)
        cmds.setAttr(mesh + ".translateY", 1)
        cmds.setAttr(mesh + ".scale", .65, 1.2, .45, type="double3")
        cmds.select(clear=True)
        root = cmds.joint(name="root_jnt", position=(0, 0, 0))
        cmds.joint(name="chest_jnt", position=(0, 1, 0))
        cmds.joint(name="tip_jnt", position=(0, 2, 0))
        cmds.parent(root, actor)
        for frame, x in ((1, -1.2), (2, 0.0), (3, 1.2)):
            cmds.setKeyframe(actor, attribute="translateX", time=frame, value=x)
        cmds.keyTangent(actor, attribute="translateX", inTangentType="linear", outTangentType="linear")

        prop = cmds.polyCube(name="HiddenPropMesh", width=1.3, height=1.6, depth=1.2)[0]
        prop_group = cmds.group(prop, name="HiddenProp_G")
        cmds.setAttr(prop_group + ".translate", 2.5, .8, -3, type="double3")

        camera, shape = cmds.camera(name="shotCam1", focalLength=35, nearClipPlane=.1, farClipPlane=1000)
        cmds.setAttr(camera + ".translate", 0, 1, 12, type="double3")
        for camera_shape in cmds.ls(type="camera"):
            cmds.setAttr(camera_shape + ".renderable", camera_shape == shape)
        cmds.setAttr("defaultResolution.width", 640)
        cmds.setAttr("defaultResolution.height", 360)
        cmds.setAttr("defaultResolution.deviceAspectRatio", 640 / 360)
        cmds.currentTime(1)
        cmds.select(clear=True)
        assert len(cmds.ls(type="mesh", long=True)) == 2
        assert len(cmds.listRelatives(actor, allDescendents=True, type="joint") or []) == 3
        assert cmds.ls("|shotCam1", type="transform")
        assert not cmds.file(query=True, reference=True)
        cmds.file(rename=str(destination))
        cmds.file(save=True, type="mayaAscii", force=False)
        assert destination.is_file()
        manifest = {
            "schema": "hmb-private-maya-smoke-fixture/v1",
            "scene": str(destination),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "camera": "|shotCam1", "frames": [1, 2, 3], "fps": 24,
            "actor_root": "|MotionActor_G", "hidden_candidate": "|HiddenProp_G",
            "mesh_count": 2, "joint_count": 3, "external_references": [],
            "scope": "Generated diagnostic geometry only; no user scene loaded or saved",
        }
        destination.with_suffix(".fixture.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print("HMB_NATIVE_SMOKE_FIXTURE=" + str(destination), flush=True)
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: mayapy _hmb_maya_smoke_fixture.py NEW_PRIVATE_SCENE.ma")
    build_scene(Path(sys.argv[1]))
