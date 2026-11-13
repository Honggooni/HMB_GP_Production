"""Exact Bash hydration success projection, actual SDK wire converter.

Private synthetic engine only. No app, provider, user workflow or installed write.
Run with the bundled SDK interpreter and -I -B.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
from unittest import mock
import weakref

ROOT = Path(__file__).resolve().parents[2]
STANDARD = Path(os.environ.get("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard")))
EDITOR = Path(os.environ.get("HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH", str(Path(os.environ["LOCALAPPDATA"]) / "ai.griptape.nodes.desktop/current/resources/editor-bundle")))
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
private = tempfile.TemporaryDirectory(prefix="hmb-bash-load-transport-")
for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
        "XDG_STATE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR",
        "GTN_CONFIG_WORKSPACE_DIRECTORY"):
    value = Path(private.name) / key
    value.mkdir()
    os.environ[key] = str(value)
os.environ["HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"] = str(STANDARD)
os.environ["HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH"] = str(STANDARD)
os.environ["HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH"] = str(EDITOR)

import _hmb_library_bootstrap as bootstrap
from HMBImageBash import HMBImageBash
from griptape_nodes.node_library.library_registry import LibraryRegistry, LibrarySchema
from griptape_nodes.retained_mode.engine import engine_scope
from griptape_nodes.retained_mode.events import converters
from griptape_nodes.retained_mode.events.base_events import EventResultFailure, EventResultSuccess, ExecutionEvent
from griptape_nodes.retained_mode.events.context_events import EnsureWorkflowAndFlowRequest
from griptape_nodes.retained_mode.events.execution_events import ParameterValueUpdateEvent
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest, SetParameterValueResultFailure,
)
from griptape_nodes.retained_mode.managers.workflow.loading import LoadProblemFrame

checks = []
def check(label, condition):
    assert condition, label
    checks.append(label)


def main():
    with engine_scope() as engine:
        engine.event_manager.initialize_queue()
        schema = LibrarySchema.model_validate_json((ROOT / "griptape-nodes-library.json").read_text("utf-8"))
        library = LibraryRegistry.generate_new_library(schema)
        definition = next(item for item in schema.nodes if item.class_name == "HMBImageBash")
        library.register_lazy_node_type("HMBImageBash", definition.metadata, lambda: HMBImageBash)
        result = engine.handle_request(EnsureWorkflowAndFlowRequest(broadcast_result=False))
        assert result.succeeded(), str(result.result_details)
        created = engine.handle_request(CreateNodeRequest(node_type="HMBImageBash", specific_library_name=schema.name,
            node_name="PrivateLoadBash", initial_setup=True, create_error_proxy_on_failure=False, broadcast_result=False))
        assert created.succeeded(), str(created.result_details)
        node = engine.node_manager.get_node_by_name(created.node_name)
        reg = bootstrap._Registration(engine, engine.event_manager)
        class Owner:
            pass
        owner = Owner()
        reg.owners[owner] = weakref.ref(library)
        node.metadata["library"], node.metadata["node_type"] = schema.name, "HMBImageBash"
        assert type(node) is HMBImageBash
        graph_identity = (id(engine.context_manager.get_current_flow()), id(node))

        def request(**kwargs):
            return SetParameterValueRequest(node_name=node.name, parameter_name="bash_image",
                value={"value": "data:image/svg+xml;base64,PHN2Zy8+", "meta": {}},
                initial_setup=True, broadcast_result=False, **kwargs)

        outside = request()
        reg._observe_workflow_load(outside)
        check("outside loading context keeps full success payload", outside.fields is None)
        # A tracked load in another task is deliberately insufficient.
        class OtherLoad:
            pass
        other = OtherLoad()
        reg.load_requests[id(other)] = weakref.ref(other)
        outside = request()
        reg._observe_workflow_load(outside)
        check("global load bookkeeping cannot substitute context-local loading", outside.fields is None)
        reg.load_requests.clear()
        with LoadProblemFrame():
            exact = request()
            original_value = exact.value
            reg._observe_workflow_load(exact)
            check("exact owned registered Bash hydration uses empty wire projection", exact.fields == [])
            check("projection retains original request value identity", exact.value is original_value)
            explicit = request(fields=["finalized_value"])
            reg._observe_workflow_load(explicit)
            check("explicit caller field selection is retained", explicit.fields == ["finalized_value"])
            explicit_empty = request(fields=[])
            reg._observe_workflow_load(explicit_empty)
            check("explicit empty projection is unchanged", explicit_empty.fields == [])
            unsupported = request()
            field_map = {key: value for key, value in SetParameterValueRequest.__dataclass_fields__.items() if key != "fields"}
            with mock.patch.object(SetParameterValueRequest, "__dataclass_fields__", field_map):
                reg._observe_workflow_load(unsupported)
            check("SDK without official fields capability retains full native reply", unsupported.fields is None)
            manual = request()
            manual.initial_setup = False
            reg._observe_workflow_load(manual)
            check("manual and live Apply requests retain full reply", manual.fields is None)
            parameter = request()
            parameter.parameter_name = "output_file"
            reg._observe_workflow_load(parameter)
            check("other Bash parameters retain full reply", parameter.fields is None)
            metadata = deepcopy(node.metadata)
            node.metadata["library"] = "ForeignLibrary"
            foreign = request()
            reg._observe_workflow_load(foreign)
            check("foreign library metadata retains full reply", foreign.fields is None)
            node.metadata = metadata
            with mock.patch.object(library, "get_node_class", return_value=type("ForeignBash", (), {})):
                foreign = request()
                reg._observe_workflow_load(foreign)
                check("foreign registered class retains full reply", foreign.fields is None)
            with mock.patch.object(bootstrap.inspect, "getfile", return_value=str(Path(private.name) / "HMBImageBash.py")):
                foreign = request()
                reg._observe_workflow_load(foreign)
                check("foreign class source path retains full reply", foreign.fields is None)
            node._hmb_node_deleted = True
            deleted = request()
            reg._observe_workflow_load(deleted)
            check("deleted retained object retains full reply", deleted.fields is None)
            node._hmb_node_deleted = False
            with mock.patch.object(engine.node_manager, "get_node_by_name", side_effect=[node, object()]):
                stale = request()
                reg._observe_workflow_load(stale)
                check("registered instance identity drift retains full reply", stale.fields is None)
            reg.owners.clear()
            foreign = request()
            reg._observe_workflow_load(foreign)
            check("ownerless registration cannot change request projection", foreign.fields is None)
            reg.owners[owner] = weakref.ref(library)
            reg.active = False
            inactive = request()
            reg._observe_workflow_load(inactive)
            check("inactive registration retains full reply", inactive.fields is None)
            reg.active = True

            # Actual native Set and converter: large synthetic metadata has no
            # executable scene, no source reads and no output generation.
            value = deepcopy(node.get_parameter_value("bash_image"))
            value.setdefault("meta", {})["transport_probe"] = "x" * (2 * 1024 * 1024)
            selected = request()
            selected.value = value
            reg._observe_workflow_load(selected)
            baseline_request = deepcopy(selected)
            baseline_request.fields = None
            result = engine.handle_request(selected)
            check("actual native initial assignment succeeds", result.succeeded())
            check("direct in-process result retains finalized scene", result.finalized_value == value)
            check("canonical Bash scene retains all synthetic data", node.get_parameter_value("bash_image") == value)
            baseline = EventResultSuccess(request=baseline_request, result=result, request_id="private-load")
            projected = EventResultSuccess(request=selected, result=result, request_id="private-load")
            conv = converters.engine
            baseline_wire, projected_wire = conv.unstructure(baseline), conv.unstructure(projected)
            original_bytes = len(json.dumps(baseline_wire).encode())
            projected_bytes = len(json.dumps(projected_wire).encode())
            check("wire success omits only finalized_value and data_type", "finalized_value" not in projected_wire["result"]
                and "data_type" not in projected_wire["result"])
            check("wire envelope preserves original complete request", projected_wire["request"]["value"] == baseline_wire["request"]["value"])
            check("wire framework success details remain exact", projected_wire["result"]["result_details"] == baseline_wire["result"]["result_details"]
                and projected_wire["result"]["altered_workflow_state"] == baseline_wire["result"]["altered_workflow_state"])
            check("large success wire is reduced approximately one half", .49 < projected_bytes / original_bytes < .51)
            failure_result = SetParameterValueResultFailure(result_details="native failure detail sentinel")
            failure = conv.unstructure(EventResultFailure(request=selected, result=failure_result, request_id="private-failure"))
            baseline_failure = conv.unstructure(EventResultFailure(request=baseline_request, result=failure_result, request_id="private-failure"))
            check("failure result remains complete regardless of fields", failure["result"] == baseline_failure["result"])
            published = []
            with mock.patch.object(engine.event_manager, "put_event", side_effect=published.append):
                node.publish_update_to_parameter("bash_image", value)
            events = [row.wrapped_event for row in published if isinstance(getattr(row, "wrapped_event", None), ExecutionEvent)
                and isinstance(row.wrapped_event.payload, ParameterValueUpdateEvent)]
            check("actual normal parameter publication emits one canonical event", len(events) == 1)
            event_wire = conv.unstructure(events[0])
            check("canonical ParameterValueUpdate event remains full and unchanged",
                events[0].payload.value == value and event_wire["payload"]["value"]["meta"]["transport_probe"] == value["meta"]["transport_probe"])
            check("graph and node identities are preserved", graph_identity == (id(engine.context_manager.get_current_flow()), id(node)))
        LibraryRegistry.unregister_library(schema.name, event_manager=engine.event_manager)
        standard_raw = json.loads((STANDARD / "griptape_nodes_library.json").read_text("utf-8"))
        standard_bash = next(item for item in standard_raw["nodes"] if item["class_name"] == "ImageBash")
        standard_source = (STANDARD / standard_bash["file_path"]).resolve()
        return {"passed": True, "count": len(checks), "checks": checks,
            "bootstrap_sha256": hashlib.sha256((ROOT / "_hmb_library_bootstrap.py").read_bytes()).hexdigest(),
            "standard_evidence": {"library_version": standard_raw["metadata"]["library_version"],
                "image_bash_sha256": hashlib.sha256(standard_source.read_bytes()).hexdigest()},
            "wire": {"unprojected_bytes": original_bytes, "projected_bytes": projected_bytes,
                "ratio": projected_bytes / original_bytes, "request_body_preserved": True},
            "scope": "actual private SDK Bash class + native Set + wire converter; no app, provider or installed writes"}


if __name__ == "__main__":
    attempts = []
    pair_context = threading.local()
    original_pair, original_connect = socket.socketpair, socket.socket.connect
    def pair(*args, **kwargs):
        pair_context.active = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            pair_context.active = False
    def deny(sock, address, *args, **kwargs):
        if getattr(pair_context, "active", False) and isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(sock, address, *args, **kwargs)
        attempts.append("blocked outbound")
        raise PermissionError("Load transport fixture blocks network")
    def deny_create(*args, **kwargs):
        attempts.append("blocked outbound")
        raise PermissionError("Load transport fixture blocks network")
    try:
        with mock.patch.object(socket, "socketpair", pair), mock.patch.object(socket.socket, "connect", deny), \
                mock.patch.object(socket.socket, "connect_ex", deny), mock.patch.object(socket, "create_connection", deny_create), \
                mock.patch.object(socket, "getaddrinfo", deny_create):
            proof = main()
        check("no outbound communication attempted", not attempts)
        proof["count"], proof["outbound_attempts"] = len(checks), len(attempts)
        print(json.dumps(proof, ensure_ascii=False))
    finally:
        logging.shutdown()
        private.cleanup()
