"""Moved image roots keep one exact project across Agent/Generator/LUT."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _hmb_project import project_from_asset_payload, resolve_project

class NestedImageRootIdentity(unittest.TestCase):
    def test_supported_direct_and_nested_collection_roots(self):
        for folder, identity in (("superwings12", "superwings12"), ("Katuri8", "katuri8")):
            for root in (f"P:/projects/{folder}/Ai_Ct_image", f"P:/projects/{folder}/Ai_Ct_image/{folder}",
                         f"//192.168.200.19/v/projects/{folder}/Ai_Ct_image", f"P:/projects/Ai_Ct_image/{folder}"):
                with self.subTest(root=root):
                    result=project_from_asset_payload({"project_id": identity, "project_root": root}, default_legacy=False)
                    self.assertEqual(result["project_id"],identity)
                    self.assertEqual(project_from_asset_payload({"project_root":root+"/"}, default_legacy=False)["project_id"],identity)
    def test_unknown_parent_and_catalog_are_not_projects(self):
        for root in ("P:/projects/Ai_Ct_image", "P:/projects/unknown/Ai_Ct_image", "P:/projects/Katuri8/../Ai_Ct_image"):
            with self.subTest(root=root), self.assertRaises(ValueError):
                project_from_asset_payload({"project_root":root}, default_legacy=False)
    def test_explicit_project_mismatch_still_fails(self):
        with self.assertRaisesRegex(ValueError,"mismatch"):
            project_from_asset_payload({"project_id":"superwings12","project_root":"P:/projects/Katuri8/Ai_Ct_image"},default_legacy=False)
        with self.assertRaisesRegex(ValueError,"project_unknown"):
            resolve_project("unknown", default_legacy=False)
    def test_nested_wire_project_inherits_and_rejects_conflicting_identity(self):
        wire={"image_asset":{"project_id":"katuri8","project_root":"P:/projects/Katuri8/Ai_Ct_image"}}
        self.assertEqual(resolve_project(wire, default_legacy=False)["project_id"],"katuri8")
        wire["project_id"]="superwings12"
        with self.assertRaisesRegex(ValueError,"mismatch"):
            resolve_project(wire,default_legacy=False)

if __name__ == "__main__": unittest.main(verbosity=2)
