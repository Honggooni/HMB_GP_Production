"""Upstream drift, editor drift and exact-host class identity boundaries."""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_image_bash_compat as compat


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CompatibilityRegression(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="hmb-image-bash-compat-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.stock = self.workspace / "standard"
        self.editor = self.workspace / "editor"
        self.source = self.stock / compat.SOURCE_RELATIVE
        self.source.parent.mkdir(parents=True)
        self.editor.mkdir()
        (self.editor / "assets").mkdir()
        self.source.write_text(
            # Inspection must never execute the source it is deciding to trust.
            "raise RuntimeError('candidate source executed during inspection')\n"
            "class ImageBash(DataNode):\n"
            "    def __init__(self):\n"
            + "".join(f"        Parameter(name={name!r})\n" for name in compat.REQUIRED_PARAMETERS if name != "bash_image")
            + "        Parameter(name='bash_image', ui_options={'modal':'ImageBashModal'}, "
              "default_value={'value':'data:fixture', 'meta':{'input_images':[], "
              "'konva_json':{'images':[], 'lines':[]}, 'viewport':{}}})\n"
            + "".join(f"    def {method}(self): pass\n" for method in compat.REQUIRED_METHODS if method != "__init__"),
            encoding="utf-8",
        )
        self.manifest = self.stock / compat.MANIFEST_NAME
        self.manifest.write_text(json.dumps({
            "name": compat.STANDARD_NAME, "metadata": {"library_version": "fixture-1"},
            "nodes": [{"class_name": "ImageBash", "file_path": compat.SOURCE_RELATIVE}],
        }), encoding="utf-8")
        (self.editor / ".version").write_text("fixture editor 1", encoding="utf-8")
        self.editor_source = "// unrelated header\n" + "\n".join(
            start + f"/* fixture {scope} */" + end
            for scope, (start, end) in compat.EDITOR_SCOPES.items()
        )
        (self.editor / "assets" / "index-fixture.js").write_text(self.editor_source, encoding="utf-8")
        (self.editor / "index-editor.html").write_text('<script src="./assets/index-fixture.js"></script>', encoding="utf-8")
        self.baseline = self.workspace / "baseline.json"
        self.baseline.write_text(json.dumps({
            "schema": compat.ADAPTER_CONTRACT,
            "standard": {"library_version": "fixture-1", "manifest_sha256": digest(self.manifest),
                         "source_sha256": digest(self.source),
                         "contract": compat.source_contract(self.source.read_text(encoding="utf-8"))},
            "editor": {"files": {".version": digest(self.editor / ".version")},
                       "bundles": {"assets/index-fixture.js": {
                           "sha256": digest(self.editor / "assets/index-fixture.js"),
                           "scopes": compat.editor_contract(self.editor_source),
                       }}},
        }), encoding="utf-8")

    def inspect(self, **options):
        return compat.inspect_standard_compatibility(
            self.stock, baseline_path=self.baseline, editor_root=self.editor, **options
        )

    def test_approved_identity_is_read_only_and_does_not_execute_source(self):
        before = {str(path.relative_to(self.workspace)): path.read_bytes()
                  for path in self.workspace.rglob("*") if path.is_file()}
        result = self.inspect()
        self.assertTrue(result["compatible"], result)
        self.assertEqual(result["editor"]["status"], "matches_baseline")
        after = {str(path.relative_to(self.workspace)): path.read_bytes()
                 for path in self.workspace.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_same_version_source_drift_is_rejected(self):
        self.source.write_text(self.source.read_text(encoding="utf-8") + "\n# upstream hotfix\n", encoding="utf-8")
        result = self.inspect()
        self.assertFalse(result["compatible"])
        self.assertTrue(any("source_sha256 changed" in value for value in result["errors"]))
        with self.assertRaises(compat.ImageBashCompatibilityError) as caught:
            compat.require_standard_compatibility(self.stock, baseline_path=self.baseline, editor_root=self.editor)
        self.assertEqual(caught.exception.diagnostics["status"], "review_required")

    def test_library_version_is_not_collected_and_unrelated_manifest_update_is_diagnostic_only(self):
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        payload["metadata"]["library_version"] = "fixture-2"
        payload["nodes"].append({"class_name": "UnrelatedNode", "file_path": "other.py"})
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        result = self.inspect()
        self.assertTrue(result["compatible"], result)
        self.assertNotIn("library_version", result["standard"])
        self.assertTrue(any("manifest_sha256 changed" in value for value in result["standard"]["observations"]))

    def test_library_version_change_cannot_approve_changed_source(self):
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        payload["metadata"]["library_version"] = "fixture-2"
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.source.write_text(self.source.read_text(encoding="utf-8") + "\n# altered source\n", encoding="utf-8")
        result = self.inspect()
        self.assertFalse(result["compatible"])
        self.assertTrue(any("source_sha256 changed" in value for value in result["errors"]))

    def test_ambiguous_duplicate_image_bash_registration_is_rejected(self):
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        payload["nodes"].append({"class_name": "ImageBash", "file_path": "other.py"})
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.assertFalse(self.inspect()["compatible"])

    def test_modal_contract_break_has_actionable_diagnostic(self):
        self.source.write_text(self.source.read_text(encoding="utf-8").replace("ImageBashModal", "ReplacementModal"), encoding="utf-8")
        self.assertTrue(any("ImageBashModal contract changed" in error for error in self.inspect()["errors"]))

    def test_removed_parameter_has_actionable_diagnostic(self):
        self.source.write_text(self.source.read_text(encoding="utf-8").replace("Parameter(name='input_images')", "Parameter(name='other')"), encoding="utf-8")
        self.assertIn("ImageBash parameter is missing: input_images", self.inspect()["errors"])

    def test_future_metadata_requires_review_instead_of_erasing_it(self):
        self.source.write_text(self.source.read_text(encoding="utf-8").replace("'viewport':{}", "'viewport':{}, 'future':{'retained':True}"), encoding="utf-8")
        contract = compat.source_contract(self.source.read_text(encoding="utf-8"))
        self.assertIn("future", contract["scene_metadata_keys"])
        result = self.inspect()
        self.assertFalse(result["compatible"])
        self.assertTrue(any("preserve/migrate saved metadata" in error for error in result["errors"]))

    def test_editor_same_filename_change_is_rejected(self):
        (self.editor / "assets" / "index-fixture.js").write_text(
            self.editor_source.replace("fixture brush_layers_load_export_modal", "changed PNG export"), encoding="utf-8"
        )
        result = self.inspect()
        self.assertEqual(result["editor"]["status"], "changed")
        self.assertFalse(result["compatible"])
        self.assertIn("Image Bash editor section changed: brush_layers_load_export_modal", result["errors"])

    def test_unrelated_header_change_is_observed_without_blocking_image_bash(self):
        (self.editor / "assets" / "index-fixture.js").write_text(
            self.editor_source.replace("// unrelated header", "// reviewed Color LUT header patch"), encoding="utf-8"
        )
        result = self.inspect()
        self.assertTrue(result["compatible"], result)
        self.assertEqual(result["editor"]["status"], "matches_contract")
        self.assertTrue(result["editor"]["bundles"]["assets/index-fixture.js"]["whole_bundle_changed"])
        self.assertEqual(len(result["editor"]["observations"]), 1)

    def test_editor_version_label_change_does_not_override_identical_reviewed_feature_regions(self):
        (self.editor / ".version").write_text("fixture editor 2", encoding="utf-8")
        self.assertTrue(self.inspect()["compatible"])

    def test_missing_or_ambiguous_section_boundary_is_rejected(self):
        first_anchor = next(iter(compat.EDITOR_SCOPES.values()))[0]
        (self.editor / "assets" / "index-fixture.js").write_text(
            self.editor_source + first_anchor, encoding="utf-8"
        )
        result = self.inspect()
        self.assertFalse(result["compatible"])
        self.assertTrue(any("anchors changed or are ambiguous" in error for error in result["errors"]))

    def test_editor_bundle_rename_is_rejected(self):
        (self.editor / "assets" / "index-fixture.js").rename(self.editor / "assets" / "index-next.js")
        self.assertFalse(self.inspect()["compatible"])

    def test_unavailable_editor_cannot_claim_full_compatibility(self):
        with mock.patch.object(compat, "resolve_editor_root", return_value=None):
            self.assertFalse(self.inspect()["compatible"])
            source_only = self.inspect(require_editor=False)
            self.assertTrue(source_only["compatible"])
            self.assertEqual(source_only["editor"]["status"], "unavailable")

    def test_active_editor_entry_cannot_escape_editor_directory(self):
        (self.editor / "index-editor.html").write_text('<script src="./assets/../../baseline.json"></script>', encoding="utf-8")
        self.assertFalse(self.inspect()["compatible"])

    def test_active_filename_change_with_identical_reviewed_regions_is_allowed(self):
        (self.editor / "assets" / "index-fixture.js").rename(self.editor / "assets" / "index-new.js")
        (self.editor / "index-editor.html").write_text('<script src="./assets/index-new.js"></script>', encoding="utf-8")
        result = self.inspect()
        self.assertTrue(result["compatible"], result)
        self.assertEqual(result["editor"]["active_bundle"], "assets/index-new.js")

    def test_active_new_bundle_must_match_reviewed_profile_not_stale_old_file(self):
        (self.editor / "assets" / "index-new.js").write_text("// unknown editor", encoding="utf-8")
        (self.editor / "index-editor.html").write_text('<script src="./assets/index-new.js"></script>', encoding="utf-8")
        self.assertFalse(self.inspect()["compatible"])

    def test_ambiguous_active_entry_is_rejected(self):
        (self.editor / "index-editor.html").write_text('<script src="./assets/index-fixture.js"></script><script src="./assets/index-new.js"></script>', encoding="utf-8")
        self.assertFalse(self.inspect()["compatible"])

    def test_additional_profile_requires_explicit_approval_and_exact_regions(self):
        payload = json.loads(self.baseline.read_text(encoding="utf-8"))
        regions = {}
        for name, (start, end) in compat.EDITOR_SCOPES.items():
            region = start + f"/* new {name} */"
            regions[name] = {"start": start, "end": end, "sha256": hashlib.sha256(region.encode()).hexdigest(), "bytes": len(region.encode())}
        payload["editor"]["profiles"] = [{"id": "future-fixture", "review_status": "pending", "regions": regions}]
        new_source = "\n".join(v["start"] + f"/* new {k} */" + v["end"] for k, v in regions.items())
        (self.editor / "assets" / "index-fixture.js").write_text(new_source, encoding="utf-8")
        self.baseline.write_text(json.dumps(payload), encoding="utf-8")
        self.assertFalse(self.inspect()["compatible"])
        payload["editor"]["profiles"][0]["review_status"] = "approved"
        self.baseline.write_text(json.dumps(payload), encoding="utf-8")
        self.assertTrue(self.inspect()["compatible"])
        (self.editor / "assets" / "index-fixture.js").write_text(new_source.replace("new modal_store", "changed modal_store"), encoding="utf-8")
        self.assertFalse(self.inspect()["compatible"])

    def test_wrong_registration_path_is_rejected(self):
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        payload["nodes"][0]["file_path"] = "../other/image_bash.py"
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        result = self.inspect()
        self.assertFalse(result["compatible"])
        self.assertTrue(any("Canonical ImageBash registration" in error for error in result["errors"]))

    def test_explicit_path_does_not_fall_back_to_another_installation(self):
        with mock.patch.dict("os.environ", {"HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH": str(self.workspace / "missing")}):
            with self.assertRaises(compat.ImageBashCompatibilityError):
                compat.resolve_standard_root()

    def test_loader_rejects_class_from_another_installation(self):
        registry_module = types.ModuleType("griptape_nodes.node_library.library_registry")
        wrong_module = types.ModuleType("hmb_fixture_wrong_stock")
        wrong_module.__file__ = str(self.workspace / "other.py")
        Path(wrong_module.__file__).write_text("# fixture", encoding="utf-8")
        candidate = type("ImageBash", (), {"__module__": wrong_module.__name__,
                                         "process": lambda self: None, "add_parameter": lambda self: None})
        registry_module.LibraryRegistry = types.SimpleNamespace(
            get_library=lambda name: types.SimpleNamespace(get_node_class=lambda node_type: candidate)
        )
        with mock.patch.dict(sys.modules, {registry_module.__name__: registry_module, wrong_module.__name__: wrong_module}):
            with self.assertRaisesRegex(compat.ImageBashCompatibilityError, "different Standard Image Bash"):
                compat.load_builtin_image_bash(self.stock, baseline_path=self.baseline, editor_root=self.editor)

    def test_loader_reuses_exact_native_registry_class(self):
        registry_module = types.ModuleType("griptape_nodes.node_library.library_registry")
        stock_module = types.ModuleType("hmb_fixture_exact_stock")
        stock_module.__file__ = str(self.source)
        candidate = type("ImageBash", (), {"__module__": stock_module.__name__,
                                         "process": lambda self: None, "add_parameter": lambda self: None})
        registry_module.LibraryRegistry = types.SimpleNamespace(
            get_library=lambda name: types.SimpleNamespace(get_node_class=lambda node_type: candidate)
        )
        with mock.patch.dict(sys.modules, {registry_module.__name__: registry_module, stock_module.__name__: stock_module}):
            loaded = compat.load_builtin_image_bash(self.stock, baseline_path=self.baseline, editor_root=self.editor)
        self.assertIs(loaded, candidate)


class WorkspaceReuseRegression(unittest.TestCase):
    """Execute the actual Asset selector; native binding has separate SDK coverage."""

    @classmethod
    def setUpClass(cls):
        path = ROOT / "HMBImageAssetLibrary.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        node_class = next(row for row in tree.body if isinstance(row, ast.ClassDef) and row.name == "HMBImageAssetLibrary")
        method = next(row for row in node_class.body if isinstance(row, ast.FunctionDef)
                      and row.name == "_create_image_bash_workspace_node")
        cls.method_code = compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec")

    def setUp(self):
        self.bash_class = type("HMBImageBash", (), {})
        self.nodes, self.created, self.bound = [], [], []
        self.workspace = {"workspace_id": "authored-workspace", "revision": 7, "instances": [{"instance_id": "same-layer"}]}
        state = {"image_bash_workspace": self.workspace, "shot_routing": {"channel_uuid": "authored-channel"}}
        self.source = types.SimpleNamespace(name="ImageAsset", lock=False, metadata={"position": {"x": 17, "y": 31}},
                                            _current_state=lambda: deepcopy(state))
        def bind(target, workspace_id):
            if getattr(target, "foreign_binding", False):
                raise ValueError("Different source already owns the native inputs")
            self.bound.append((target, workspace_id))
        self.source._hmb_bind_image_bash_workspace = bind
        scope = {"_normalize_image_bash_workspace_request": lambda value: deepcopy(value),
                 "_hmb_shot_routing": types.SimpleNamespace(_same_flow_nodes=lambda node: ("own-flow", self.nodes)),
                 "WIDGET_LIBRARY_NAME": "HMB_GP_Production", "ASSET_NODE_WIDTH": 1320}
        exec(self.method_code, scope)
        self.select = scope["_create_image_bash_workspace_node"]
        self.command = {"workspace_id": self.workspace["workspace_id"], "expected_revision": self.workspace["revision"]}
        def create(request):
            self.created.append(request)
            target = self.bash("CreatedBash")
            self.nodes.append(target)
            return types.SimpleNamespace(succeeded=lambda: True, node_name=target.name)
        sdk = types.ModuleType("griptape_nodes.retained_mode.griptape_nodes")
        sdk.GriptapeNodes = types.SimpleNamespace(handle_request=create,
            NodeManager=lambda: types.SimpleNamespace(get_node_by_name=lambda name: next(node for node in self.nodes if node.name == name)))
        events = types.ModuleType("griptape_nodes.retained_mode.events.node_events")
        events.CreateNodeRequest = lambda **values: types.SimpleNamespace(**values)
        registry = types.ModuleType("griptape_nodes.node_library.library_registry")
        def library(kind, owner):
            self.assertEqual((kind, owner), ("HMBImageBash", "HMB_GP_Production"))
            return types.SimpleNamespace(get_node_class=lambda kind: self.bash_class)
        registry.LibraryRegistry = types.SimpleNamespace(get_library_for_node_type=library)
        patch = mock.patch.dict(sys.modules, {module.__name__: module for module in (sdk, events, registry)})
        patch.start()
        self.addCleanup(patch.stop)

    def bash(self, name, *, owner="HMB_GP_Production", kind=None):
        node = (kind or self.bash_class)()
        node.name = name
        node.metadata = {"library": owner, "node_type": "HMBImageBash"}
        node.scene = {"layers": [{"x": 0, "opacity": 0}], "apply_receipt": {"sha256": "authored"}}
        node.output = "existing-output.png"
        return node

    def test_unbound_palette_node_is_reused_with_scene_output_and_workspace_preserved(self):
        target = self.bash("PaletteFirst")
        self.nodes.append(target)
        before = deepcopy((vars(target), self.workspace))
        self.assertEqual(self.select(self.source, self.command), target.name)
        self.assertEqual(self.created, [])
        self.assertEqual(self.bound, [(target, self.workspace["workspace_id"])])
        self.assertEqual((vars(target), self.workspace), before)

    def test_matching_bound_node_is_reused_without_new_create(self):
        target = self.bash("Existing")
        target.metadata.update(hmb_image_bash_workspace_id=self.workspace["workspace_id"],
                               hmb_image_bash_channel_uuid="authored-channel")
        self.nodes.append(target)
        self.assertEqual(self.select(self.source, self.command), target.name)
        self.assertEqual(self.created, [])
        self.assertIs(self.bound[0][0], target)

    def test_foreign_same_named_class_is_preserved_and_never_reused(self):
        foreign = self.bash("Foreign", owner="OtherLibrary", kind=type("HMBImageBash", (), {}))
        self.nodes.append(foreign)
        before = deepcopy(vars(foreign))
        self.assertEqual(self.select(self.source, self.command), "CreatedBash")
        self.assertEqual(len(self.created), 1)
        self.assertIsNot(self.bound[0][0], foreign)
        self.assertEqual(vars(foreign), before)

    def test_multiple_legacy_editors_are_preserved_without_choosing_or_creating(self):
        self.nodes.extend((self.bash("AuthoredA"), self.bash("AuthoredB")))
        before = deepcopy([vars(node) for node in self.nodes])
        with self.assertRaises(ValueError):
            self.select(self.source, self.command)
        self.assertEqual(self.created, [])
        self.assertEqual(self.bound, [])
        self.assertEqual([vars(node) for node in self.nodes], before)

    def test_foreign_native_binding_is_not_stolen_or_replaced(self):
        target = self.bash("AlreadyOwned")
        target.foreign_binding = True
        self.nodes.append(target)
        before = deepcopy(vars(target))
        with self.assertRaises(ValueError):
            self.select(self.source, self.command)
        self.assertEqual(self.created, [])
        self.assertEqual(vars(target), before)

    def test_stale_workspace_command_does_not_create_or_rebind(self):
        self.nodes.append(self.bash("Existing"))
        with self.assertRaises(ValueError):
            self.select(self.source, dict(self.command, expected_revision=6))
        self.assertEqual((self.created, self.bound), ([], []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
