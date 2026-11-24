"""Exercise a specific Local HMB library using its Desktop Python, without Standard."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

TESTS = Path(__file__).resolve().parents[1] / "resources/tests"


def fingerprint(path):
    return sha256(path.read_bytes()).hexdigest()


class AbsentStandard:
    def __init__(self):
        self.attempts = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] == "griptape_nodes_library":
            self.attempts.append(fullname)
            raise ModuleNotFoundError(fullname)
        return None


async def exercise_sdk(engine, library_path, stack):
    import _hmb_library_bootstrap as bootstrap
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.traits.widget import Widget
    from HMB_Desktop031_Workflow_Envelope_Host_Regression import check_basket_envelopes, draft_final

    schema = LibrarySchema.model_validate_json((library_path / "griptape-nodes-library.json").read_bytes())
    library = LibraryRegistry.generate_new_library(schema)
    classes = {}
    for row in schema.nodes:
        module = importlib.import_module(Path(row.file_path).stem)
        assert Path(module.__file__).resolve() == (library_path / row.file_path).resolve()
        cls = getattr(module, row.class_name)
        library.register_lazy_node_type(row.class_name, row.metadata, lambda cls=cls: cls)
        classes[row.class_name] = cls
    assert len(classes) == 11
    # Scope the product handlers to this isolated engine. External server start
    # and writes to the user's installed editor are outside this fixture.
    stack.enter_context(patch.object(bootstrap._Registration, "start_web_worker", return_value=None))
    stack.enter_context(patch.object(bootstrap, "_hmb_coordinate_native_editor_update", return_value=None))
    owner = bootstrap.HMBProductionLibrary.__new__(bootstrap.HMBProductionLibrary)
    owner._registrations = set()
    owner.before_library_nodes_loaded(schema, library)
    engine.event_manager.initialize_queue()
    stack.callback(owner.before_library_unregistered, schema, library)

    async def send(request, workflow=None):
        request.broadcast_result = False
        return await engine.ahandle_request(request, result_context={"open_workflow_id": workflow} if workflow else {})

    await check_basket_envelopes(engine, send)
    test_tabs = []
    for label in ("Independent Draft", "Independent shot"):
        tab = await send(EnsureWorkflowAndFlowRequest(flow_name=label))
        assert tab.succeeded(), tab.result_details
        test_tabs.append(engine.open_workflows.get(tab.workflow_id))
    # This exercises the installed Final callback and bound normal generation
    # through an offline request recorder. No provider or broker is contacted.
    with patch.object(sys, "path", list(sys.path)):
        await draft_final(engine, *test_tabs)
    opened = await send(EnsureWorkflowAndFlowRequest(flow_name="Independent library"))
    assert opened.succeeded(), opened.result_details
    runtime = engine.open_workflows.get(opened.workflow_id)
    widgets, node_names = [], []
    with engine.bind_workflow(runtime):
        for name, cls in classes.items():
            created = await send(CreateNodeRequest(node_type=name, node_name=name, specific_library_name=schema.name,
                create_error_proxy_on_failure=False), runtime.workflow_id)
            assert created.succeeded(), (name, created.result_details)
            node = engine.node_manager.get_node_by_name_in(runtime, created.node_name)
            assert type(node) is cls
            if name == "HMBAgentLibrary":
                assert any(parent.__module__ == "_hmb_native_agent.agents.agent" for parent in cls.__mro__), cls.__mro__
                assert node.get_parameter_by_name("model") and node._model_access.model_choices
            node_names.append(name)
            for parameter in node.parameters:
                if not isinstance(parameter, Parameter):
                    continue
                for trait in parameter.find_elements_by_type(Widget, find_recursively=True):
                    if trait.library != schema.name:
                        continue
                    widgets.append({"name": trait.name, "node": name, "parameter": parameter.name,
                        "options": trait.ui_options_for_trait(), "value": node.get_parameter_value(parameter.name),
                        "synced": {key: node.get_parameter_value(key) for key in (trait.synced_parameters or [])},
                        "binding": "native"})
    bound_names = {w["name"] for w in widgets}
    registered_names = {row.name for row in schema.widgets}
    # The VideoPicker dashboard uses the command parameter directly. Its registered
    # legacy bridge can still be mounted explicitly by an older saved node.
    bridge = "HMBVideoPickerCommandBridgeWidget"
    assert bound_names == registered_names - {bridge}, {"missing": registered_names-bound_names, "extra": bound_names-registered_names}
    picker = engine.node_manager.get_node_by_name_in(runtime, "HMBVideoPickerLibrary")
    command = picker.get_parameter_by_name("HMB_PICKER_COMMAND")
    assert command is not None and command.hide_property
    widgets.append({"name": bridge, "node": picker.name, "parameter": command.name,
        "options": {"widget": bridge, "library": schema.name}, "value": picker.get_parameter_value(command.name),
        "binding": "registered legacy module, explicit mount"})
    assert len(schema.widgets) == 13
    return {"nodes": node_names, "widgets": widgets, "basket_create_reopen": True,
        "offline_draft_final_requests": 1, "offline_bound_shot_requests": 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--desktop", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--stage-overlay", type=Path, help="Reviewed candidate overlay for a stock staging editor")
    parser.add_argument("--expected-version", default="0.9.46")
    args = parser.parse_args()
    root, desktop, output = (item.resolve() for item in (args.library, args.desktop, args.out))
    output.mkdir(parents=True, exist_ok=True)
    python = desktop / "resources/engine-bundle/python/python.exe"
    assert Path(sys.executable).resolve() == python, f"Use the selected Desktop Python: {python}"
    sys.path[:0] = [str(root), str(TESTS)]
    manifest = root / "griptape-nodes-library.json"
    data = json.loads(manifest.read_bytes())
    assert data["metadata"]["library_version"] == args.expected_version
    assert (root / "_hmb_native_agent/UPSTREAM.json").is_file()
    sys.dont_write_bytecode = True
    # Keep actual Electron/Chrome user variables available only for Playwright;
    # the SDK and all nodes below see an isolated, empty home and workspace.
    browser_env = dict(os.environ)
    with TemporaryDirectory(prefix="hmb-isolated-", ignore_cleanup_errors=True) as temporary, ExitStack() as stack:
        scratch = Path(temporary)
        env = {}
        for key in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                    "XDG_STATE_HOME", "XDG_CACHE_HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY", "GTN_ENGINE_CONFIG_DIR",
                    "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR", "HMB_IMAGE_PROJECTS_ROOT"):
            (scratch / key).mkdir()
            env[key] = str(scratch / key)
        missing = str(scratch / "uninstalled-standard")
        env.update(HMB_GRIPTAPE_STANDARD_LIBRARY_PATH=missing, HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH=missing,
                   HMB_MODE_TEST_LIBRARY_ROOT=str(root))
        stack.enter_context(patch.dict(os.environ, env))
        guard = AbsentStandard()
        stack.enter_context(patch.object(sys, "meta_path", [guard, *sys.meta_path]))
        stack.enter_context(patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")))
        from griptape_nodes.retained_mode.engine import engine_scope
        with engine_scope() as engine:
            result = asyncio.run(exercise_sdk(engine, root, stack))
        assert not guard.attempts, guard.attempts
        assert not any(k.split(".", 1)[0] == "griptape_nodes_library" for k in sys.modules)
        assert all(Path(module.__file__).resolve().is_relative_to(root) for name, module in sys.modules.items()
                   if name.split(".", 1)[0] == "_hmb_native_agent" and getattr(module, "__file__", None))
        result["agent_module"] = str(Path(sys.modules["_hmb_native_agent.agents.agent"].__file__).resolve())
    sdk = output / "sdk.json"
    sdk.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    from restore_rodong_local_editor import EDITOR_1320, entry_for_overlay, stock_entry_from_active
    editor = python.parent / "Lib/site-packages/griptape_nodes_editor_dist/editor"
    stock = editor / "assets" / EDITOR_1320.bundle
    assert fingerprint(stock) == EDITOR_1320.stock_digest
    entry = (editor / "index-editor.html").read_bytes()
    if args.stage_overlay:
        overlay = args.stage_overlay.resolve()
    else:
        active = re.search(rb'<script type="module" crossorigin src="\./assets/(index-hmb-rodong-[a-f0-9]+\.js)">', entry)
        assert active, "HMB editor entry is not active"
        overlay = editor / "assets" / active.group(1).decode("ascii")
    expected_name = "index-hmb-rodong-" + fingerprint(overlay)[:16] + ".js"
    baseline = stock_entry_from_active(entry, expected_name)
    assert sha256(baseline).hexdigest() == EDITOR_1320.entry_digest
    if not args.stage_overlay:
        assert overlay.name == expected_name and entry == entry_for_overlay(baseline, expected_name)
    stock_entry = output / "reviewed-stock-entry.html"
    stock_entry.write_bytes(baseline)
    browser_env.update(HMB_STOCK_EDITOR_0130_SOURCE=str(stock), HMB_HEADER_0130_CANDIDATE=str(overlay),
        HMB_LIFECYCLE_REPORT_DIR=str(output), HMB_REVIEWED_STOCK_ENTRY=str(stock_entry),
        HMB_INDEPENDENT_LIBRARY=str(root), HMB_INDEPENDENT_SDK_DATA=str(sdk))
    node = shutil.which("node")
    assert node, "Node.js is required for the isolated Chromium checks"
    for test in ("_hmb_independent_widget_container.mjs", "HMB_Editor_0130_Integrated_Header_Regression.mjs",
                 "HMB_Editor_0132_Rodong_Launch_Regression.mjs"):
        subprocess.run([node, str(TESTS / test)], check=True, cwd=output, env=browser_env, timeout=90)
    proof = {"passed": True, "library": str(root), "version": args.expected_version, "manifest_sha256": fingerprint(manifest),
        "nodes": len(result["nodes"]), "widgets": len(data["widgets"]), "external_standard_imports": guard.attempts,
        "active_installed_overlay": not bool(args.stage_overlay), "overlay_sha256": fingerprint(overlay),
        "surface": "Isolated installed SDK and headless official Editor components; separate in-memory Desktop bridge"}
    (output / "summary.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
