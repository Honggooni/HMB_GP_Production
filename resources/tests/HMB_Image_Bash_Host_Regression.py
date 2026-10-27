"""HMB Image Bash in the installed SDK, with disposable PNG/source fixtures.

Native CreateNode/SetParameterValue, serialization, file output, save and a
fresh deserialized node are real. The Apply payload is an explicitly synthetic
editor-shaped PNG/scene fixture; this test does not claim browser UI execution.
No installed library, user workflow, live app, network or provider is changed.
"""
from __future__ import annotations

import ast
import asyncio
import base64
from copy import deepcopy
import faulthandler
import hashlib
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest import mock
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
STANDARD = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
EDITOR = Path(os.environ.get("HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH") or (
    Path(os.environ.get("LOCALAPPDATA", "")) / "ai.griptape.nodes.desktop/current/resources/editor-bundle"))
ATTEMPTS = []


def deny_network(*_args, **_kwargs):
    ATTEMPTS.append("unexpected_network")
    raise AssertionError("Image Bash SDK fixture must not access the network")


def send(engine, request):
    request.broadcast_result = False
    result = engine.handle_request(request)
    assert result.succeeded(), str(result.result_details)
    return result


def png_bytes(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def exercise(engine, directory):
    from PIL import Image
    import HMBImageBash as target
    from griptape_nodes.exe_types.core_types import ParameterMode
    from griptape_nodes.exe_types.node_types import NodeResolutionState
    from griptape_nodes.files.file import File
    from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
    from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
    from griptape_nodes.retained_mode.events.execution_events import ResolveNodeRequest, ResolveNodeResultSuccess
    from griptape_nodes.retained_mode.events.flow_events import (
        DeleteFlowRequest, DeserializeFlowFromCommandsRequest, SerializeFlowToCommandsRequest,
    )
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
    from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowFileFromSerializedFlowRequest

    document = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8-sig"))
    if not any(row["class_name"] == "HMBImageBash" for row in document["nodes"]):
        # Development-time temporary registration only; the shipping manifest
        # is owned by the main integration task and is never edited here.
        definition = deepcopy(document["nodes"][0])
        definition.update(class_name="HMBImageBash", file_path="HMBImageBash.py")
        document["nodes"].append(definition)
    schema = LibrarySchema.model_validate(document)
    library = LibraryRegistry.generate_new_library(schema)
    definition = next(row for row in schema.nodes if row.class_name == "HMBImageBash")
    library.register_lazy_node_type("HMBImageBash", definition.metadata, lambda: target.HMBImageBash)
    engine.event_manager.initialize_queue()
    ensured = send(engine, EnsureWorkflowAndFlowRequest(display_name="Synthetic Image Bash SDK",
                                                       flow_name="ImageBashSDKRegression"))
    created = send(engine, CreateNodeRequest(node_type="HMBImageBash", node_name="Synthetic Image Bash",
        specific_library_name=schema.name, initial_setup=True, create_error_proxy_on_failure=False))
    node = engine.node_manager.get_node_by_name(created.node_name)

    def set_value(name, value, *, owner=None, initial=False):
        current = node if owner is None else owner
        return send(engine, SetParameterValueRequest(node_name=current.name,
                    parameter_name=name, value=deepcopy(value), initial_setup=initial))

    def set_inputs(records):
        parameter = node.get_parameter_by_name("input_images")
        children = list(parameter.get_child_parameters())
        while len(children) < len(records):
            children.append(parameter.add_child_parameter())
        for child, record in zip(children, records):
            set_value(child.name, {"value": record["url"], "type": "ImageUrlArtifact"})

    try:
        assert node.get_parameter_value("comp_on_run") is False
        editor_options = node.get_parameter_by_name("bash_image").ui_options
        assert editor_options["modal"] == "ImageBashModal"
        assert editor_options["button_label"] == "Open HMBImageBash Editor"
        # ParameterList.ui_options returns a copy. Verify the constructor used
        # its setter rather than mutating a discarded getter dictionary.
        images_options = node.get_parameter_by_name("input_images").ui_options
        assert images_options.get("hide") is True and images_options.get("hide_handles") is True
        context_options = node.get_parameter_by_name("image_bash_context").ui_options
        assert context_options.get("hide") is True and context_options.get("hide_handles") is True
        for name in ("canvas_size", "width", "height", "background_color", "comp_on_run", "output_file"):
            parameter = node.get_parameter_by_name(name)
            assert parameter.ui_options.get("hide_handles") is True, name
            assert ParameterMode.PROPERTY in parameter.allowed_modes, (name, parameter.allowed_modes)
            assert ParameterMode.INPUT in parameter.allowed_modes, (name, parameter.allowed_modes)
        assert ParameterMode.OUTPUT in node.get_parameter_by_name("width").allowed_modes
        assert ParameterMode.OUTPUT in node.get_parameter_by_name("height").allowed_modes
        set_value("width", 4)
        set_value("height", 2)
        set_value("background_color", "#ffffff")
        source_a, source_b, brush_path = (directory / leaf for leaf in ("source-a.png", "source-b.png", "brush.png"))
        Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(source_a)
        Image.new("RGBA", (2, 2), (0, 0, 255, 128)).save(source_b)
        Image.new("RGBA", (4, 2), (0, 255, 0, 50)).save(brush_path)
        records = [{"source_uid": "fixture-asset-a", "url": str(source_a), "name": "Authored red",
                    "media_signature": hashlib.sha256(source_a.read_bytes()).hexdigest()},
                   {"source_uid": "fixture-asset-b", "url": str(source_b), "name": "Authored blue",
                    "media_signature": hashlib.sha256(source_b.read_bytes()).hexdigest()}]
        context = {"schema": target.CONTEXT_SCHEMA, "workspace_id": "fixture-image-bash-workspace",
                   "revision": 1, "records": records}
        set_inputs(records)
        set_value("image_bash_context", context)
        project = deepcopy(node.get_parameter_value("bash_image"))
        assert len(project["meta"]["konva_json"]["images"]) == 2, {
            "project": project, "status": node.get_parameter_value("HMB_BASH_STATUS"),
            "inputs": node.get_parameter_value("input_images"),
            "list_inputs": node.get_parameter_list_value("input_images"),
            "context": node.get_parameter_value("image_bash_context")}
        editor_urls = {row["source_uid"]: row["url"] for row in project["meta"]["input_images"]}
        for uid, original in (("fixture-asset-a", source_a), ("fixture-asset-b", source_b)):
            editor_url = editor_urls[uid]
            assert urlparse(editor_url).scheme == "http"
            assert urlparse(editor_url).hostname in {"localhost", "127.0.0.1"}
            assert urlparse(editor_url).path.endswith(".png")
            assert ".griptape-nodes-previews" not in editor_url and ".webp" not in editor_url
            assert Path(File(editor_url).resolve()) == original
            assert File(editor_url).read_bytes() == original.read_bytes()
        assert [layer["src"] for layer in project["meta"]["konva_json"]["images"]] == [
            editor_urls["fixture-asset-a"], editor_urls["fixture-asset-b"]]
        assert node.get_parameter_value("image_bash_context")["records"] == records
        assert [target._url(value) for value in node.get_parameter_value("input_images")] == [str(source_a), str(source_b)]
        first, second = project["meta"]["konva_json"]["images"]
        first.update(x=1.0, y=1.0, width=2, height=2, opacity=0, scaleX=-1, rotation=0, order=0)
        second.update(x=3.0, y=1.0, width=2, height=2, opacity=0.5, rotation=0, order=1)
        duplicated = deepcopy(second)
        duplicated.update(id="fixture-duplicate-layer", x=1.0, opacity=1, order=2)
        brush = {"id": "brush-fixture", "type": "brush", "src": str(brush_path), "canvas": {},
                 "x": 2.0, "y": 1.0, "width": 4, "height": 2, "scaleX": 1, "scaleY": 1,
                 "opacity": 1, "visible": True, "rotation": 0, "order": 3,
                 "future_brush_metadata": {"pen": 0, "eraser": False}}
        project["meta"]["konva_json"]["images"].extend([duplicated, brush])
        project["meta"]["konva_json"]["future_scene"] = {"retain": True}
        project["meta"]["viewport"] = {"x": 42.25, "y": -8, "scale": 1.3}
        project["meta"]["created_at"] = "2026-10-23T01:01:01.001Z"
        # The actual editor emits one input_images row per image occurrence,
        # including a duplicate source ID for a duplicated canvas layer.
        project["meta"]["input_images"].extend([deepcopy(project["meta"]["input_images"][1]),
            {"id": brush["id"], "url": str(brush_path), "name": "Synthetic brush"}])
        expected_image = Image.new("RGBA", (4, 2))
        expected_image.putdata([(30, 50, 220, 255), (70, 100, 200, 255), (200, 100, 0, 255), (60, 80, 90, 255)] * 2)
        applied_png = png_bytes(expected_image)
        project["value"] = "data:image/png;base64," + base64.b64encode(applied_png).decode("ascii")
        project["name"] = "Synthetic browser-shaped Apply fixture"
        set_value("bash_image", project)
        committed = deepcopy(node.get_parameter_value("bash_image"))
        receipt = committed["meta"]["hmb_image_bash"]["apply"]
        assert receipt["png_sha256"] == hashlib.sha256(applied_png).hexdigest()
        assert len(committed["meta"]["konva_json"]["images"]) == 4
        assert committed["meta"]["viewport"] == project["meta"]["viewport"]
        assert committed["meta"]["konva_json"]["images"][-1] == brush
        output_path = directory / "run-output.png"
        set_value("output_file", str(output_path))
        # SDK hydration can materialize a different root JsonArtifact object.
        # Envelope identity is not layer/source identity or authored pixels.
        materialized = deepcopy(committed)
        materialized["id"] = "0123456789abcdef0123456789abcdef"
        materialized["reference"] = "synthetic-sdk-envelope-reference"
        set_value("bash_image", materialized)
        assert node.get_parameter_value("bash_image")["meta"]["hmb_image_bash"]["apply"] == receipt
        assert node.get_parameter_value("bash_image")["meta"]["konva_json"] == committed["meta"]["konva_json"]
        committed = deepcopy(node.get_parameter_value("bash_image"))
        # A native upstream refresh can replace optional cache metadata with
        # a resolver-descriptor signature without changing any source byte.
        # Verify this before the fixture's existing first native scheduler run.
        # A second scheduler start after delete/deserialization is deliberately
        # avoided; actual app context restoration is a separate live UI check.
        before_signature = deepcopy(committed)
        signature_context = deepcopy(node.get_parameter_value("image_bash_context"))
        source_bytes_before = {record["source_uid"]: File(record["url"]).read_bytes()
                               for record in signature_context["records"]}
        previous_signatures = [record["media_signature"] for record in signature_context["records"]]
        for record in signature_context["records"]:
            record["media_signature"] = hashlib.sha256(
                ("resolver-descriptor:" + record["source_uid"] + ":" + record["url"]).encode()).hexdigest()
        assert [record["media_signature"] for record in signature_context["records"]] != previous_signatures
        set_value("image_bash_context", signature_context)
        refreshed_signature = deepcopy(node.get_parameter_value("bash_image"))
        assert refreshed_signature["meta"]["konva_json"] == before_signature["meta"]["konva_json"]
        assert refreshed_signature["meta"]["hmb_image_bash"]["apply"] == before_signature["meta"]["hmb_image_bash"]["apply"]
        assert {record["source_uid"]: File(record["url"]).read_bytes()
                for record in signature_context["records"]} == source_bytes_before
        context = deepcopy(signature_context)
        records = deepcopy(signature_context["records"])
        committed = refreshed_signature
        print("CHECKPOINT SDK envelope identity + optional signature refresh preserved receipt; starting first native Resolve", flush=True)
        resolved = await asyncio.wait_for(engine.ahandle_request(ResolveNodeRequest(
            node_name=node.name, broadcast_result=False)), timeout=15)
        assert isinstance(resolved, ResolveNodeResultSuccess), {
            "result_type": type(resolved).__name__, "details": str(resolved.result_details),
            "validation": [str(item) for item in getattr(resolved, "validation_exceptions", [])]}
        assert node.state == NodeResolutionState.RESOLVED, node.state
        output = node.parameter_output_values["output_image"]
        assert output and File(output.value).read_bytes() == applied_png
        assert output.value.startswith(("http://", "https://")), "Native preview must receive an original-file browser URL"
        assert "preview=true" not in output.value.lower()
        assert Path(File(output.value).resolve()) == output_path.resolve()
        assert node.get_parameter_value("HMB_BASH_VERIFICATION")["output"] == str(output_path)
        with Image.open(output_path) as output_image:
            assert output_image.convert("RGBA").tobytes() == expected_image.tobytes()
        assert node.get_parameter_value("HMB_BASH_VERIFICATION")["apply_pixel_equal"] is True
        print("PASS actual SDK envelope + media_signature-only refresh then Resolve validates/schedules Run; original PNG bytes/RGBA match without metadata reinjection; hidden UI/labels retained", flush=True)

        # Direct original-file HTTP URLs bypass the native modal's lossy
        # preview conversion, while ImageAsset values keep Windows paths.
        # Real SDK-readable C: and file:// aliases still identify those same
        # raster bytes and must not cause an extra rejected Apply cycle.
        assert File(source_a.as_uri()).read_bytes() == source_a.read_bytes()
        assert File(source_b.as_uri()).read_bytes() == source_b.read_bytes()
        aliased = deepcopy(committed)
        original_paths = {"fixture-asset-a": str(source_a), "fixture-asset-b": source_b.as_uri()}
        for layer in aliased["meta"]["konva_json"]["images"]:
            if layer.get("type") == "image":
                layer["src"] = original_paths[layer["source_uid"]]
        for source in aliased["meta"]["input_images"]:
            if source.get("source_uid") in {"fixture-asset-a", "fixture-asset-b"}:
                source["url"] = original_paths[source["source_uid"]]
        aliased["meta"]["created_at"] = "2026-10-23T01:01:01.002Z"
        set_value("bash_image", aliased)
        committed = deepcopy(node.get_parameter_value("bash_image"))
        assert all(layer["src"] == editor_urls[layer["source_uid"]] for layer in
                   committed["meta"]["konva_json"]["images"] if layer.get("type") == "image")
        assert [row["url"] for row in committed["meta"]["input_images"]
                if row.get("source_uid") in original_paths] == [editor_urls["fixture-asset-a"], editor_urls["fixture-asset-b"]]
        assert node.get_parameter_value("image_bash_context")["records"] == records
        node.process()
        assert File(node.parameter_output_values["output_image"].value).read_bytes() == applied_png
        print("PASS editor HTTP sources resolve/read exact original PNG with no WEBP previews or network; ImageAsset paths stay intact and file/C: aliases commit once", flush=True)

        # Painting an existing brush exports a new raster URL. That changed
        # brush and its newly painted Apply PNG are intentional authored data,
        # while the ImageAsset inputs remain unchanged and freshness-checked.
        external_before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (source_a, source_b)]
        painted_brush_path = directory / "brush-painted-new-export.png"
        painted_brush = Image.new("RGBA", (4, 2), (0, 0, 0, 0))
        painted_brush.putpixel((0, 0), (240, 30, 210, 180))
        painted_brush.putpixel((3, 1), (255, 190, 20, 255))
        painted_brush.save(painted_brush_path)
        painted = deepcopy(committed)
        for layer in painted["meta"]["konva_json"]["images"]:
            if layer.get("id") == "brush-fixture":
                layer["src"] = painted_brush_path.as_uri()
        for source in painted["meta"]["input_images"]:
            if source.get("id") == "brush-fixture":
                source["url"] = painted_brush_path.as_uri()
        old_png = applied_png
        expected_image = expected_image.copy()
        expected_image.putpixel((0, 0), (220, 40, 190, 255))
        expected_image.putpixel((3, 1), (255, 190, 20, 255))
        applied_png = png_bytes(expected_image)
        assert applied_png != old_png
        painted["value"] = "data:image/png;base64," + base64.b64encode(applied_png).decode("ascii")
        painted["meta"]["created_at"] = "2026-10-23T01:01:01.003Z"
        set_value("bash_image", painted)
        committed = deepcopy(node.get_parameter_value("bash_image"))
        assert committed["meta"]["konva_json"]["images"][-1]["src"] == painted_brush_path.as_uri()
        assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in (source_a, source_b)] == external_before
        node.process()
        verified_output = File(node.parameter_output_values["output_image"].value)
        assert verified_output.read_bytes() == applied_png
        output_path = Path(verified_output.resolve())
        with Image.open(output_path) as actual:
            assert actual.convert("RGBA").tobytes() == expected_image.tobytes()
        print("PASS existing brush new raster URL and painted Apply pixels commit in one event while external ImageAsset bytes stay unchanged", flush=True)

        # Native editor deletion removes all occurrences of one selected asset.
        # Its ImageAsset selection stays selected; later sync/reopen must not
        # invent a layer absent from the applied PNG.
        deleted = deepcopy(committed)
        deleted["meta"]["konva_json"]["images"] = [layer for layer in
            deleted["meta"]["konva_json"]["images"] if layer.get("source_uid") != "fixture-asset-a"]
        deleted["meta"]["input_images"] = [row for row in deleted["meta"]["input_images"]
                                               if row.get("source_uid") != "fixture-asset-a"]
        deleted["meta"]["created_at"] = "2026-10-23T01:01:02.002Z"
        set_value("bash_image", deleted)
        committed = deepcopy(node.get_parameter_value("bash_image"))
        assert len(committed["meta"]["konva_json"]["images"]) == 3
        assert "fixture-asset-a" in committed["meta"]["hmb_image_bash"]["suppressed_source_uids"]
        node.process()
        assert File(node.parameter_output_values["output_image"].value).read_bytes() == applied_png
        print("PASS deleting every occurrence of a selected source remains deleted after Apply and subsequent source sync", flush=True)

        # Reordering the input list must preserve every source-owned transform.
        before_positions = {layer["id"]: (layer["x"], layer["y"], layer["opacity"])
                            for layer in committed["meta"]["konva_json"]["images"]}
        reversed_context = deepcopy(context)
        reversed_context["records"].reverse()
        reversed_context["revision"] += 1
        set_inputs(reversed_context["records"])
        set_value("image_bash_context", reversed_context)
        reordered = node.get_parameter_value("bash_image")
        assert {layer["id"]: (layer["x"], layer["y"], layer["opacity"])
                for layer in reordered["meta"]["konva_json"]["images"]} == before_positions
        assert node.get_parameter_value("output_image") is None
        # The real editor retains unknown HMB metadata and marks a fresh Apply
        # with a new created_at, even when the PNG bytes happen to be identical.
        reapplied = deepcopy(reordered)
        reapplied["meta"]["created_at"] = "2026-10-23T01:02:02.002Z"
        set_value("bash_image", reapplied)
        committed = deepcopy(node.get_parameter_value("bash_image"))

        # The advanced flag can only publish after the corrected metadata
        # renderer also matches Apply. This arbitrary fixture intentionally
        # differs from its layer composite, so the existing file must survive.
        set_value("comp_on_run", True)
        original_output = output_path.read_bytes()
        try:
            node.process()
        except ValueError as exc:
            assert "Apply" in str(exc) and "픽셀" in str(exc), str(exc)
        else:
            raise AssertionError("Advanced Run published a render with different pixels than Apply")
        assert node.parameter_output_values.get("output_image") is None
        assert output_path.read_bytes() == original_output

        # Independently calculated source-over pixels: blue alpha128 over
        # white on the left; blue alpha64 (opacity 0.5) on the right. Disable
        # the flattened brush. Distinct PNG compression proves Run copies the
        # approved bytes rather than replacing them with a re-encoded result.
        positive = deepcopy(committed)
        positive["meta"]["konva_json"]["images"][-1]["opacity"] = 0
        expected_image = Image.new("RGBA", (4, 2))
        expected_image.putdata(([(127, 127, 255, 255)] * 2 + [(191, 191, 255, 255)] * 2) * 2)
        encoded = BytesIO()
        expected_image.save(encoded, format="PNG", compress_level=0)
        applied_png = encoded.getvalue()
        assert png_bytes(expected_image) != applied_png
        positive["value"] = "data:image/png;base64," + base64.b64encode(applied_png).decode("ascii")
        positive["meta"]["created_at"] = "2026-10-23T01:03:03.003Z"
        set_value("bash_image", positive)
        committed = deepcopy(node.get_parameter_value("bash_image"))
        receipt = committed["meta"]["hmb_image_bash"]["apply"]
        node.process()
        verified_output = File(node.parameter_output_values["output_image"].value)
        assert verified_output.read_bytes() == applied_png
        output_path = Path(verified_output.resolve())
        with Image.open(output_path) as actual:
            assert actual.convert("RGBA").tobytes() == expected_image.tobytes()
        assert node.get_parameter_value("HMB_BASH_VERIFICATION")["apply_pixel_equal"] is True
        set_value("comp_on_run", False)
        print("PASS advanced Run blocks different Apply pixels; matching alpha composite publishes the exact original PNG encoding", flush=True)

        # An editor can stay open while ImageAsset replaces a selected source.
        # Committing its old PNG/URL must fail, then the synchronized scene can
        # be reopened and a single new Apply accepted for the replacement.
        stale_modal = deepcopy(committed)
        replacement = directory / "source-b-replaced.png"
        Image.new("RGBA", (2, 2), (0, 255, 0, 128)).save(replacement)
        replaced_context = deepcopy(reversed_context)
        replaced_context["revision"] += 1
        for record in replaced_context["records"]:
            if record["source_uid"] == "fixture-asset-b":
                record["url"] = str(replacement)
        set_inputs(replaced_context["records"])
        set_value("image_bash_context", replaced_context)
        stale_modal["meta"]["created_at"] = "2026-10-23T01:04:04.004Z"
        failed_apply = engine.handle_request(SetParameterValueRequest(node_name=node.name,
            parameter_name="bash_image", value=stale_modal, broadcast_result=False))
        assert not failed_apply.succeeded(), "Stale modal PNG was committed after source URL replacement"
        assert node.parameter_output_values.get("output_image") is None
        assert output_path.read_bytes() == applied_png
        refreshed = deepcopy(node.get_parameter_value("bash_image"))
        for layer in refreshed["meta"]["konva_json"]["images"]:
            if layer.get("source_uid") == "fixture-asset-b":
                assert urlparse(layer["src"]).scheme == "http"
                assert ".griptape-nodes-previews" not in layer["src"] and ".webp" not in layer["src"]
                assert Path(File(layer["src"]).resolve()) == replacement
                assert File(layer["src"]).read_bytes() == replacement.read_bytes()
        expected_image = Image.new("RGBA", (4, 2))
        expected_image.putdata(([(127, 255, 127, 255)] * 2 + [(191, 255, 191, 255)] * 2) * 2)
        applied_png = png_bytes(expected_image)
        refreshed["value"] = "data:image/png;base64," + base64.b64encode(applied_png).decode("ascii")
        refreshed["meta"]["created_at"] = "2026-10-23T01:05:05.005Z"
        set_value("bash_image", refreshed)
        committed = deepcopy(node.get_parameter_value("bash_image"))
        receipt = committed["meta"]["hmb_image_bash"]["apply"]
        node.process()
        output_path = Path(File(node.parameter_output_values["output_image"].value).resolve())
        assert output_path.read_bytes() == applied_png
        print("PASS source URL changes while editor is open reject stale Apply; synchronized scene accepts one refreshed Apply", flush=True)

        # Native save captures the authoritative receipt/embedded PNG. Delete
        # the graph, create a fresh node from native commands, then Run again.
        serialized = send(engine, SerializeFlowToCommandsRequest(flow_name=ensured.flow_name,
            include_create_flow_command=True)).serialized_flow_commands
        save_path = directory / "synthetic-image-bash-workflow.py"
        save_result = await engine.ahandle_request(SaveWorkflowFileFromSerializedFlowRequest(
            serialized_flow_commands=serialized, file_name=save_path.stem, file_path=str(save_path),
            display_name="Synthetic Image Bash SDK only", broadcast_result=False))
        assert save_result.succeeded(), str(save_result.result_details)
        tree = ast.parse(save_path.read_text(encoding="utf-8"), filename=str(save_path))
        compile(tree, str(save_path), "exec")
        assert receipt["png_base64"] in save_path.read_text(encoding="utf-8")
        old_node = node
        send(engine, DeleteFlowRequest(flow_name=ensured.flow_name))
        reopened = await engine.ahandle_request(DeserializeFlowFromCommandsRequest(
            serialized_flow_commands=serialized, broadcast_result=False))
        assert reopened.succeeded(), str(reopened.result_details)
        flow = engine.flow_manager.get_flow_by_name(reopened.flow_name)
        node = flow.nodes[created.node_name]
        assert node is not old_node
        restored_project = node.get_parameter_value("bash_image")
        assert restored_project == committed, (restored_project, committed)
        assert node.get_parameter_value("comp_on_run") is False
        node.process()
        verified_output = File(node.parameter_output_values["output_image"].value)
        assert verified_output.read_bytes() == applied_png
        output_path = Path(verified_output.resolve())
        assert all(layer.get("source_uid") != "fixture-asset-a" for layer in
                   restored_project["meta"]["konva_json"]["images"])
        print("PASS actual SDK serialize/native save/delete/cold deserialize; full scene+viewport+brush+receipt restored; Run bytes remain identical", flush=True)

        # ImageAsset retains the last good image values while a newer source
        # resolution fails. Its ready=False context must revoke Run authority
        # without deleting the saved scene/receipt or emitting another file.
        current_context = deepcopy(node.get_parameter_value("image_bash_context"))
        ready_context = deepcopy(current_context)
        ready_context["ready"] = True
        unavailable = deepcopy(current_context)
        unavailable.update(ready=False, requested_revision=int(current_context.get("revision", 0)) + 1)
        scene_before_unavailable = deepcopy(node.get_parameter_value("bash_image"))
        saved_files = {path.name: path.read_bytes() for path in directory.glob("run-output*.png")}
        set_value("image_bash_context", unavailable)
        assert node.get_parameter_value("bash_image") == scene_before_unavailable
        try:
            node.process()
        except ValueError as exc:
            assert "ImageAsset" in str(exc), str(exc)
        else:
            raise AssertionError("ready=False context authorized a previous good image list")
        assert node.parameter_output_values.get("output_image") is None
        assert node.get_parameter_value("HMB_BASH_VERIFICATION") == {}
        assert {path.name: path.read_bytes() for path in directory.glob("run-output*.png")} == saved_files
        set_value("image_bash_context", ready_context)
        assert node.get_parameter_value("bash_image") == scene_before_unavailable
        node.process()
        assert File(node.parameter_output_values["output_image"].value).read_bytes() == applied_png

        # A different workspace cannot inherit a saved Apply receipt even if
        # its ordered URLs/source records happen to match byte for byte.
        foreign_workspace = deepcopy(ready_context)
        foreign_workspace["workspace_id"] = "fixture-other-image-bash-workspace"
        saved_files = {path.name: path.read_bytes() for path in directory.glob("run-output*.png")}
        set_value("image_bash_context", foreign_workspace)
        assert node.get_parameter_value("bash_image") == scene_before_unavailable
        try:
            node.process()
        except ValueError as exc:
            assert "Apply" in str(exc), str(exc)
        else:
            raise AssertionError("An unrelated workspace reused another workspace's Apply receipt")
        assert node.parameter_output_values.get("output_image") is None
        assert {path.name: path.read_bytes() for path in directory.glob("run-output*.png")} == saved_files
        set_value("image_bash_context", ready_context)
        assert node.get_parameter_value("bash_image") == scene_before_unavailable
        node.process()
        verified_output = File(node.parameter_output_values["output_image"].value)
        assert verified_output.read_bytes() == applied_png
        output_path = Path(verified_output.resolve())
        print("PASS unresolved ready=False blocks stale image transport; different workspace cannot reuse Apply; source scene survives and original ready workspace resumes", flush=True)

        original_output = output_path.read_bytes()
        # A valid embedded receipt must not authorize different project.value
        # pixels under the same retained Apply marker.
        tampered = deepcopy(restored_project)
        tampered["value"] = "data:image/png;base64," + base64.b64encode(
            png_bytes(Image.new("RGBA", (4, 2), (1, 2, 3, 255)))).decode("ascii")
        rejected = engine.handle_request(SetParameterValueRequest(node_name=node.name,
            parameter_name="bash_image", value=tampered, broadcast_result=False))
        # Cold-restore hydration may defer validation to Run until all input
        # parameters arrive. In either path it must never publish new output.
        if rejected.succeeded():
            try:
                node.process()
            except ValueError:
                pass
            else:
                raise AssertionError("Tampered project.value was authorized by the embedded receipt")
        assert node.parameter_output_values.get("output_image") is None
        assert output_path.read_bytes() == original_output
        set_value("bash_image", restored_project)
        node.process()
        print("PASS retained Apply receipt cannot authorize tampered exported PNG pixels", flush=True)
        source_a.write_bytes(png_bytes(Image.new("RGBA", (2, 2), (1, 2, 3, 255))))
        try:
            node.process()
        except ValueError as exc:
            assert "변경" in str(exc), str(exc)
        else:
            raise AssertionError("Changed source content was accepted with an old Apply receipt")
        assert node.parameter_output_values.get("output_image") is None
        assert output_path.read_bytes() == original_output
        print("PASS same URL with changed source bytes invalidates Apply and leaves previous complete output untouched", flush=True)

        # Advanced metadata composition must fail before output save as well.
        source_a.unlink()
        set_value("comp_on_run", True)
        try:
            node.process()
        except Exception:
            pass
        else:
            raise AssertionError("Missing layer yielded a partial composite")
        assert node.parameter_output_values.get("output_image") is None
        assert output_path.read_bytes() == original_output
        assert not ATTEMPTS, ATTEMPTS
        print(json.dumps({"status": "PASS", "scope": "installed SDK synthetic fixtures", "pixel_equal": True,
            "native_parameter_events": True, "native_save_cold_reopen": True,
            "native_resolve_node_validation_scheduling": True,
            "native_file_uri_raster_alias_single_apply": True, "painted_brush_new_raster_single_apply": True,
            "editor_initial_original_http_input_contract_preserved": True,
            "native_hidden_ui_options_and_editor_label": True,
            "resolver_media_signature_only_refresh_native_resolve": True,
            "sdk_root_envelope_identity_preserves_apply": True,
            "duplicate_layers_and_brush": True, "stable_source_reorder": True,
            "intentional_layer_deletion_preserved": True, "receipt_value_tamper_blocked": True,
            "advanced_match_exact_png": True, "advanced_pixel_mismatch_blocked": True,
            "stale_modal_source_replacement_rejected_then_reapplied": True,
            "unready_context_blocks_previous_images": True, "workspace_apply_isolation": True,
            "source_content_change_blocked": True, "failed_load_no_partial_output": True,
            "live_browser_ui_verified": False, "network_calls": 0}, sort_keys=True), flush=True)
    finally:
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)


def main():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="hmb-image-bash-host-") as folder:
        directory = Path(folder)
        env = {key: str(directory / key) for key in (
            "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
            "XDG_STATE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR",
            "GTN_CONFIG_WORKSPACE_DIRECTORY")}
        env.update(HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH=str(STANDARD),
                   HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH=str(EDITOR))
        for key, value in env.items():
            if key not in {"HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH", "HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH"}:
                Path(value).mkdir()
        with mock.patch.dict(os.environ, env), mock.patch.object(socket, "create_connection", deny_network):
            os.chdir(directory)
            logging.disable(logging.CRITICAL)
            faulthandler.enable()
            faulthandler.dump_traceback_later(25, exit=True)
            print("CHECKPOINT isolated SDK host regression starting; hard watchdog 25 seconds", flush=True)
            try:
                from griptape_nodes.retained_mode.engine import engine_scope
                with engine_scope() as engine:
                    asyncio.run(exercise(engine, directory))
            finally:
                faulthandler.cancel_dump_traceback_later()
                os.chdir(previous)
                logging.shutdown()


if __name__ == "__main__":
    main()
