# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import os
import shutil
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAYA_DIR = os.path.join(ROOT, "resources", "maya")
if MAYA_DIR not in sys.path:
    sys.path.insert(0, MAYA_DIR)

import maya.standalone

maya.standalone.initialize(name="python")

import maya.cmds as cmds
import HMBVideoPicker_Test_8Objects as fixture
import HMB_Maya_Background_Preview as runner


def main():
    test_dir = tempfile.mkdtemp(prefix=".HMB_Asset_Root_Filter_", dir=ROOT)
    try:
        scene_path = os.path.join(test_dir, "HMBVideoPicker_Test_8Objects.mb")
        fixture.build_scene(scene_path)
        cmds.file(scene_path, open=True, force=True, executeScriptNodes=False)
        nodes = runner._scan_outliner_nodes()
        names = [str(item.get("name") or "") for item in nodes]
        paths = [str(item.get("full_path") or "") for item in nodes]

        expected_names = {
            "HMB_Test_Cube",
            "HMB_Test_Cylinder",
            "HMB_Test_Sphere",
            "HMB_Test_Cone",
            "HMB_Test_Torus",
            "HMB_Test_Pyramid",
            "HMB_Test_Prism",
            "HMB_Test_Capsule_GRP",
            "HMB_Test_Ground",
        }
        assert set(names) == expected_names, (names, paths)
        assert len(nodes) == 9, nodes
        assert all(item.get("asset_root") is True for item in nodes)
        assert all(item.get("outliner_filter") == "asset_roots_v1" for item in nodes)
        assert all(not item.get("parent_path") for item in nodes)
        assert all(int(item.get("depth") or 0) == 0 for item in nodes)
        assert "|HMB_Test_Objects_GRP" not in paths
        print("HMB live Maya asset-root filter regression: PASS ({0} roots)".format(len(nodes)))
    finally:
        try:
            cmds.file(new=True, force=True)
        except Exception:
            pass
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
