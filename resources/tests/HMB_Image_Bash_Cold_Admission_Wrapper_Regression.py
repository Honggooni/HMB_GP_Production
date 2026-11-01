"""Read-only AST review of the request wrapper with a fake SDK boundary.

Imports no actual SDK, app, project/credential configuration or media. This
tests wrapper lifecycle and helper admission; actual native cold replay is
owned by the independent compiled/SDK fixture, not this test.
"""
from __future__ import annotations
import ast
import asyncio
from copy import deepcopy
import contextvars
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "HMBImageBash.py"
raw_source = SOURCE.read_bytes()
tree = ast.parse(raw_source.decode("utf-8-sig"))
wrapper_ast = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_install_bash_initial_value_admission")
klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HMBImageBash")
helper_ast = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == "_admit_pending_cold_assignment")
helper_ast.decorator_list = []


class SetParameterValueRequest:
    def __init__(self, *, node_name="Bash", parameter_name="bash_image", initial_setup=True, is_output=False):
        self.node_name, self.parameter_name = node_name, parameter_name
        self.initial_setup, self.is_output = initial_setup, is_output


FAKE_MODULES = {}
for name in ("griptape_nodes", "griptape_nodes.retained_mode", "griptape_nodes.retained_mode.events",
             "griptape_nodes.retained_mode.events.parameter_events", "griptape_nodes.retained_mode.engine",
             "griptape_nodes.retained_mode.griptape_nodes"):
    FAKE_MODULES[name] = ModuleType(name)
FAKE_MODULES["griptape_nodes.retained_mode.events.parameter_events"].SetParameterValueRequest = SetParameterValueRequest
CURRENT = None
HAS_ENGINE = True
FAKE_MODULES["griptape_nodes.retained_mode.engine"].has_current_engine = lambda: HAS_ENGINE
FAKE_MODULES["griptape_nodes.retained_mode.griptape_nodes"].GriptapeNodes = SimpleNamespace(
    EventManager=lambda: CURRENT.event_manager, NodeManager=lambda: CURRENT.node_manager)


def namespace():
    values = {"Any": Any, "contextvars": contextvars, "inspect": inspect, "_document": deepcopy,
              "_hmb_is_registered_node": lambda node, kind: getattr(node, "registered", False) and kind == "HMBImageBash"}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper_ast, helper_ast], type_ignores=[])), str(SOURCE), "exec"), values)
    return values


NS = namespace()


def draft():
    return {"value": "data:image/png;base64,c2F2ZWQ=", "meta": {"created_at": "saved-draft",
        "konva_json": {"images": [], "lines": []}, "input_images": [],
        "hmb_image_bash": {"pending_apply": {"schema": "hmb-image-bash-pending-apply-v1", "editor_commit": "saved-draft"}}}}


class Node:
    _admit_pending_cold_assignment = NS["_admit_pending_cold_assignment"]
    def __init__(self, name="Bash", registered=True):
        self.name, self.registered = name, registered
        self.value = {"value": "", "meta": {}}
        self._hmb_auto_pristine_project = deepcopy(self.value)
        self._hmb_prepare_phase, self._hmb_apply_epoch = "idle", 0
        self._hmb_last_output = self._hmb_apply_pending = self._hmb_prepare_pending = None
    def get_parameter_value(self, name):
        assert name == "bash_image"
        return self.value


def engine(original):
    global CURRENT
    nodes = {"Bash": Node(), "Other": Node("Other", registered=False)}
    def get(name):
        if name not in nodes:
            raise ValueError(name)
        return nodes[name]
    CURRENT = SimpleNamespace(event_manager=SimpleNamespace(_request_type_to_manager={SetParameterValueRequest: original}),
                              node_manager=SimpleNamespace(get_node_by_name=get), nodes=nodes)
    return CURRENT


class AdmissionReview(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(sys.modules, FAKE_MODULES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def install(self, original):
        current = engine(original)
        NS["_install_bash_initial_value_admission"](current)
        return current, current.event_manager._request_type_to_manager[SetParameterValueRequest]

    def test_sync_passthrough_exact_result_and_lease_scope(self):
        seen, saved = [], []
        sentinel = object()
        def original(request):
            variable = CURRENT.event_manager._hmb_bash_initial_assignment_context
            seen.append((request, variable.get()["node"], variable.get()["active"]))
            saved.append(contextvars.copy_context())
            return sentinel
        current, wrapped = self.install(original)
        for request in (SetParameterValueRequest(), SetParameterValueRequest(node_name="Other"),
                        SetParameterValueRequest(initial_setup=False), SetParameterValueRequest(parameter_name="width"),
                        SetParameterValueRequest(node_name="Missing")):
            self.assertIs(wrapped(request), sentinel)
        self.assertIs(seen[0][1], current.nodes["Bash"])
        self.assertTrue(all(row[2] for row in seen))
        self.assertTrue(all(row[1] is None for row in seen[1:]))
        variable = current.event_manager._hmb_bash_initial_assignment_context
        self.assertIsNone(variable.get())
        self.assertTrue(all(saved_context.run(variable.get)["active"] is False for saved_context in saved))

    def test_sync_exception_restores_context(self):
        def original(request):
            raise ValueError("original failure")
        current, wrapped = self.install(original)
        with self.assertRaisesRegex(ValueError, "original failure"):
            wrapped(SetParameterValueRequest())
        self.assertIsNone(current.event_manager._hmb_bash_initial_assignment_context.get())

    def test_nested_noninitial_masks_outer_then_restores_it(self):
        observed = []
        def original(request):
            variable = CURRENT.event_manager._hmb_bash_initial_assignment_context
            if request.initial_setup:
                outer = variable.get()
                wrapped(SetParameterValueRequest(initial_setup=False))
                self.assertIs(variable.get(), outer)
                self.assertTrue(outer["active"])
            else:
                observed.append(variable.get()["node"])
        current, wrapped = self.install(original)
        wrapped(SetParameterValueRequest())
        self.assertEqual(observed, [None])
        self.assertIsNone(current.event_manager._hmb_bash_initial_assignment_context.get())

    def test_reload_idempotence_and_foreign_handler_chain(self):
        calls = []
        def original(request): calls.append("original"); return 73
        current, first = self.install(original)
        variable = current.event_manager._hmb_bash_initial_assignment_context
        namespace()["_install_bash_initial_value_admission"](current)
        self.assertIs(current.event_manager._request_type_to_manager[SetParameterValueRequest], first)
        def foreign(request): calls.append("foreign"); return first(request)
        current.event_manager._request_type_to_manager[SetParameterValueRequest] = foreign
        namespace()["_install_bash_initial_value_admission"](current)
        self.assertIs(current.event_manager._hmb_bash_initial_assignment_context, variable)
        latest = current.event_manager._request_type_to_manager[SetParameterValueRequest]
        self.assertEqual(latest(SetParameterValueRequest()), 73)
        self.assertEqual(calls, ["foreign", "original"])
        self.assertIsNone(variable.get())

    def test_async_wrapper_keeps_lease_during_await_and_invalidates_copy(self):
        saved = []
        async def original(request):
            variable = CURRENT.event_manager._hmb_bash_initial_assignment_context
            saved.append(contextvars.copy_context())
            await asyncio.sleep(0)
            self.assertTrue(variable.get()["active"])
            self.assertIs(variable.get()["node"], CURRENT.nodes["Bash"])
            return 91
        current, wrapped = self.install(original)
        self.assertTrue(inspect.iscoroutinefunction(wrapped))
        self.assertEqual(asyncio.run(wrapped(SetParameterValueRequest())), 91)
        variable = current.event_manager._hmb_bash_initial_assignment_context
        self.assertFalse(saved[0].run(variable.get)["active"])
        self.assertIsNone(variable.get())

    def test_async_exception_invalidates_captured_lease(self):
        saved = []
        async def original(request):
            saved.append(contextvars.copy_context())
            await asyncio.sleep(0)
            raise ValueError("async original failure")
        current, wrapped = self.install(original)
        with self.assertRaisesRegex(ValueError, "async original failure"):
            asyncio.run(wrapped(SetParameterValueRequest()))
        variable = current.event_manager._hmb_bash_initial_assignment_context
        self.assertFalse(saved[0].run(variable.get)["active"])
        self.assertIsNone(variable.get())

    def test_pristine_pending_admit_and_idempotent_output(self):
        document = draft()
        def original(request):
            node = CURRENT.nodes[request.node_name]
            accepted = node._admit_pending_cold_assignment(document)
            node.value = deepcopy(document)
            return accepted
        current, wrapped = self.install(original)
        self.assertTrue(wrapped(SetParameterValueRequest()))
        document["id"], document["reference"] = "sdk-id", "sdk-reference"
        self.assertTrue(wrapped(SetParameterValueRequest(is_output=True)))
        document["meta"]["konva_json"]["lines"].append({"points": [0, 1]})
        self.assertFalse(wrapped(SetParameterValueRequest(is_output=True)))

    def test_initial_request_required_even_with_marker_and_pristine(self):
        document = draft()
        def original(request): return CURRENT.nodes["Bash"]._admit_pending_cold_assignment(document)
        current, wrapped = self.install(original)
        self.assertFalse(wrapped(SetParameterValueRequest(initial_setup=False)))
        self.assertFalse(current.nodes["Bash"]._admit_pending_cold_assignment(document))

    def test_copied_request_context_cannot_admit_after_handler_returns(self):
        saved = []
        def original(request): saved.append(contextvars.copy_context())
        current, wrapped = self.install(original)
        wrapped(SetParameterValueRequest())
        self.assertFalse(saved[0].run(current.nodes["Bash"]._admit_pending_cold_assignment, draft()))

    def test_live_or_malformed_pending_not_admitted(self):
        cases = [lambda node, doc: setattr(node, "_hmb_apply_epoch", 1),
                 lambda node, doc: setattr(node, "_hmb_prepare_phase", "ready"),
                 lambda node, doc: setattr(node, "_hmb_last_output", {}),
                 lambda node, doc: setattr(node, "_hmb_prepare_pending", {}),
                 lambda node, doc: doc["meta"]["hmb_image_bash"]["pending_apply"].update(schema="wrong"),
                 lambda node, doc: doc["meta"]["hmb_image_bash"]["pending_apply"].update(editor_commit="wrong"),
                 lambda node, doc: doc["meta"].update(konva_json={"images": ["bad"], "lines": []})]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                document = draft()
                def original(request): return CURRENT.nodes["Bash"]._admit_pending_cold_assignment(document)
                current, wrapped = self.install(original)
                mutate(current.nodes["Bash"], document)
                self.assertFalse(wrapped(SetParameterValueRequest()))


    def test_pending_prepare_exact_shape_and_revision_type(self):
        for revision, accepted in ((3, True), (True, False), (-1, False), ("3", False)):
            with self.subTest(revision=revision):
                document = draft()
                document["meta"]["hmb_image_bash"] = {"pending_prepare": {
                    "schema": "hmb-image-bash-pending-prepare-v1", "scope": {
                        "workspace_id": "workspace", "channel_uuid": "channel", "workspace_revision": revision},
                    "source_uids": ["source-a"]}}
                def original(request): return CURRENT.nodes["Bash"]._admit_pending_cold_assignment(document)
                current, wrapped = self.install(original)
                self.assertEqual(wrapped(SetParameterValueRequest()), accepted)

    def test_node_replacement_during_original_handler_rejects_prior_instance(self):
        def original(request):
            old = CURRENT.nodes["Bash"]
            CURRENT.nodes["Bash"] = Node()
            return old._admit_pending_cold_assignment(draft())
        current, wrapped = self.install(original)
        self.assertFalse(wrapped(SetParameterValueRequest()))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AdmissionReview)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    output = {"source_path": str(SOURCE), "source_sha256": hashlib.sha256(raw_source).hexdigest(),
              "scope": "actual methods AST extraction; fake SDK request boundary; no actual cold UI replay",
              "tests": result.testsRun, "errors": len(result.errors), "failures": len(result.failures),
              "passed": result.wasSuccessful()}
    output_path = Path(os.environ.get("HMB_BASH_COLD_WRAPPER_REPORT_DIR", str(ROOT / "reports/regression-checks/HMB_Image_Bash_Cold_Admission_Wrapper_Regression"))) / "COLD-ADMISSION-WRAPPER.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    raise SystemExit(not result.wasSuccessful())
