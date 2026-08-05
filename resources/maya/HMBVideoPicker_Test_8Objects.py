# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import math
import os
import random
import sys


def _initialize_maya():
    try:
        import maya.cmds as cmds  # noqa: F401
        if callable(getattr(cmds, "file", None)):
            return
    except Exception:
        pass
    import maya.standalone
    maya.standalone.initialize(name="python")


_initialize_maya()

import maya.cmds as cmds

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import HMB_Maya_Binding_Setup as hmb_setup


OBJECT_SPECS = [
    ("HMB_Test_Cube", "Red", "Test_Cube", "cube"),
    ("HMB_Test_Cylinder", "Green", "Test_Cylinder", "cylinder"),
    ("HMB_Test_Sphere", "Blue", "Test_Sphere", "sphere"),
    ("HMB_Test_Cone", "Yellow", "Test_Cone", "cone"),
    ("HMB_Test_Torus", "Orange", "Test_Torus", "torus"),
    ("HMB_Test_Pyramid", "Purple", "Test_Pyramid", "pyramid"),
    ("HMB_Test_Prism", "Pink", "Test_Prism", "prism"),
    ("HMB_Test_Capsule", "Sky Blue", "Test_Capsule", "capsule"),
]


def _create_primitive(kind, name):
    if kind == "cube":
        return cmds.polyCube(name=name, width=2.1, height=2.1, depth=2.1, constructionHistory=False)[0]
    if kind == "cylinder":
        return cmds.polyCylinder(name=name, radius=1.15, height=2.7, subdivisionsAxis=20, constructionHistory=False)[0]
    if kind == "sphere":
        return cmds.polySphere(name=name, radius=1.3, subdivisionsX=20, subdivisionsY=12, constructionHistory=False)[0]
    if kind == "cone":
        return cmds.polyCone(name=name, radius=1.35, height=2.8, subdivisionsAxis=20, constructionHistory=False)[0]
    if kind == "torus":
        return cmds.polyTorus(name=name, radius=1.25, sectionRadius=0.38, subdivisionsX=24, subdivisionsY=10, constructionHistory=False)[0]
    if kind == "pyramid":
        try:
            return cmds.polyPyramid(name=name, width=2.4, height=2.8, sideLength=4, constructionHistory=False)[0]
        except Exception:
            return cmds.polyCone(name=name, radius=1.55, height=2.8, subdivisionsAxis=4, constructionHistory=False)[0]
    if kind == "prism":
        return cmds.polyCylinder(name=name, radius=1.4, height=2.6, subdivisionsAxis=6, constructionHistory=False)[0]
    if kind == "capsule":
        cylinder = cmds.polyCylinder(name=name, radius=0.9, height=2.2, subdivisionsAxis=20, constructionHistory=False)[0]
        top = cmds.polySphere(name=name + "_Top", radius=0.9, subdivisionsX=20, subdivisionsY=10, constructionHistory=False)[0]
        bottom = cmds.polySphere(name=name + "_Bottom", radius=0.9, subdivisionsX=20, subdivisionsY=10, constructionHistory=False)[0]
        cmds.setAttr(top + ".translateY", 1.1)
        cmds.setAttr(bottom + ".translateY", -1.1)
        root = cmds.group(cylinder, top, bottom, name=name + "_GRP")
        return root
    raise RuntimeError("Unknown primitive kind: {0}".format(kind))


def _animate(root, index, rng):
    start = 1
    middle = 36
    end = 72
    base_x = cmds.getAttr(root + ".translateX")
    base_y = cmds.getAttr(root + ".translateY")
    base_z = cmds.getAttr(root + ".translateZ")
    phase = rng.uniform(0.0, math.pi * 2.0)
    amplitude = rng.uniform(0.35, 1.0)
    spin = rng.choice([-1.0, 1.0]) * rng.uniform(70.0, 190.0)
    drift_x = math.cos(phase) * amplitude
    drift_z = math.sin(phase) * amplitude

    for frame, offset_y, rotate_y, offset_x, offset_z in (
        (start, 0.0, 0.0, 0.0, 0.0),
        (middle, amplitude, spin * 0.5, drift_x, drift_z),
        (end, 0.0, spin, -drift_x * 0.35, -drift_z * 0.35),
    ):
        cmds.setKeyframe(root, attribute="translateX", time=frame, value=base_x + offset_x)
        cmds.setKeyframe(root, attribute="translateY", time=frame, value=base_y + offset_y)
        cmds.setKeyframe(root, attribute="translateZ", time=frame, value=base_z + offset_z)
        cmds.setKeyframe(root, attribute="rotateY", time=frame, value=rotate_y)
        cmds.setKeyframe(root, attribute="rotateX", time=frame, value=(index + 1) * 4.0 if frame == middle else 0.0)
    cmds.keyTangent(root, inTangentType="spline", outTangentType="spline")


def _create_camera():
    camera, shape = cmds.camera(name="HMB_Test_ShotCamera")
    cmds.setAttr(camera + ".translateX", 15.0)
    cmds.setAttr(camera + ".translateY", 12.0)
    cmds.setAttr(camera + ".translateZ", 20.0)
    cmds.setAttr(shape + ".focalLength", 42.0)
    target = cmds.spaceLocator(name="HMB_Test_CameraTarget")[0]
    cmds.setAttr(target + ".translateY", 1.0)
    cmds.aimConstraint(target, camera, aimVector=(0, 0, -1), upVector=(0, 1, 0), worldUpType="scene")
    for camera_shape in cmds.ls(type="camera") or []:
        cmds.setAttr(camera_shape + ".renderable", camera_shape == shape)
    return camera


def build_scene(output_path=None):
    rng = random.Random(314159)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")
    cmds.playbackOptions(minTime=1, maxTime=72, animationStartTime=1, animationEndTime=72)

    scene_root = cmds.group(empty=True, name="HMB_Test_Objects_GRP")
    positions = [
        (-5.0, 1.3, -3.0),
        (-1.7, 1.5, -3.7),
        (2.0, 1.4, -3.0),
        (5.3, 1.5, -3.8),
        (-4.7, 1.2, 1.8),
        (-1.6, 1.5, 2.3),
        (2.1, 1.4, 1.8),
        (5.1, 1.5, 2.4),
    ]

    roots = []
    for index, (name, color, asset_id, kind) in enumerate(OBJECT_SPECS):
        root = _create_primitive(kind, name)
        cmds.parent(root, scene_root)
        x, y, z = positions[index]
        cmds.setAttr(root + ".translateX", x + rng.uniform(-0.25, 0.25))
        cmds.setAttr(root + ".translateY", y)
        cmds.setAttr(root + ".translateZ", z + rng.uniform(-0.25, 0.25))
        cmds.setAttr(root + ".rotateY", rng.uniform(-25.0, 25.0))
        scale = rng.uniform(0.85, 1.2)
        cmds.setAttr(root + ".scaleX", scale)
        cmds.setAttr(root + ".scaleY", scale)
        cmds.setAttr(root + ".scaleZ", scale)
        _animate(root, index, rng)
        roots.append((root, color, asset_id))

    ground = cmds.polyPlane(name="HMB_Test_Ground", width=18.0, height=12.0, subdivisionsX=1, subdivisionsY=1, constructionHistory=False)[0]
    cmds.setAttr(ground + ".translateY", 0.0)
    camera = _create_camera()

    data_node = hmb_setup.create_data_node(clear_existing=True)
    for root, color, asset_id in roots:
        hmb_setup.create_binding(
            root=root,
            color=color,
            asset_id=asset_id,
            display_name=asset_id,
            enabled=True,
            data_node=data_node,
        )
    hmb_setup.register_camera(camera, data_node=data_node)
    report = hmb_setup.validate()

    if not output_path:
        output_path = os.path.join(SCRIPT_DIR, "HMBVideoPicker_Test_8Objects.mb")
    output_path = os.path.abspath(os.path.expanduser(os.path.expandvars(output_path)))
    output_folder = os.path.dirname(output_path)
    if output_folder and not os.path.isdir(output_folder):
        os.makedirs(output_folder)
    if not output_path.lower().endswith(".mb"):
        output_path += ".mb"
    # Maya can expand the playback range while animation and constraints are
    # authored. Reassert the intended fixture range immediately before save.
    cmds.playbackOptions(
        minTime=1,
        maxTime=72,
        animationStartTime=1,
        animationEndTime=72,
    )
    cmds.currentTime(1, edit=True)
    cmds.file(rename=output_path)
    cmds.file(save=True, type="mayaBinary", force=True)
    print("HMBVideoPicker test scene saved: {0}".format(output_path))
    print("Bindings: {0}".format(len(report["bindings"])))
    return output_path


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else None
    build_scene(output_path)


if __name__ == "__main__":
    main()
