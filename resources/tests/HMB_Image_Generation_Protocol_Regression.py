"""Offline image Broker contract, reference bytes and durable-result checks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import base64
import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import io
import json
import random
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_image_generation as images
from PIL import Image

assert "HMBSeedanceGeneration" not in sys.modules, "Pure image validation imported the video/native runtime"
checks = 1


def check(condition: bool, message: str = "") -> None:
    global checks
    assert condition, message
    checks += 1


def rejects(action, code: str = "") -> images.ImageGenerationError:
    global checks
    try:
        action()
    except images.ImageGenerationError as exc:
        if code:
            assert exc.code == code, (exc.code, code)
        checks += 1
        return exc
    raise AssertionError("Invalid image operation was accepted")


def image_bytes(image_format: str = "PNG", size=(13, 7)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (20, 90, 150)).save(buffer, image_format)
    return buffer.getvalue()


PNG = image_bytes()
RAW_CAPS = {
    "schema": images.CAPABILITIES_SCHEMA, "version": 1, "enabled": True,
    "persistence_scope": "personal_local",
    "client_request_lookup": True,
    "models": [{"provider": "example-image-provider", "model_id": "future-image-model",
                "display_name": "Any server-registered image model", "enabled": True, "credential_ready": True,
                "tasks": ["text-to-image", "image-to-image"], "aspect_ratios": ["1:1", "16:9"],
                "image_sizes": ["1K", "2K"], "output_formats": ["png", "jpeg", "webp"],
                "max_reference_images": 3, "max_reference_bytes": 1024 * 1024}]}
CAPS = images.parse_capabilities(RAW_CAPS)
OPTIONS = dict(model_id="future-image-model", task="text-to-image", prompt="손글씨와 캐릭터를 정확히 유지",
               ratio="16:9", image_size="1K", output_format="png")
INVOCATION = images.prepare_invocation(CAPS, **OPTIONS)
check(INVOCATION.provider == "example-image-provider")
check(INVOCATION.payload()["prompt"] == OPTIONS["prompt"])
detached = INVOCATION.payload()
detached["prompt"] = "changed"
check(INVOCATION.payload()["prompt"] == OPTIONS["prompt"], "Frozen invocation changed with the live UI")
check(INVOCATION.client_request_id.startswith("img-"))
for field, value in (("schema", "other"), ("version", True), ("enabled", 1), ("persistence_scope", "web_reviews"), ("models", {})):
    bad = copy.deepcopy(RAW_CAPS)
    bad[field] = value
    rejects(lambda: images.parse_capabilities(bad))
for field, value in (("credential_ready", "yes"), ("enabled", 1), ("max_reference_images", True),
                     ("max_reference_bytes", -1), ("output_formats", ["mov"]), ("tasks", ["video"]),
                     ("aspect_ratios", ["1:1", "1:1"])):
    bad = copy.deepcopy(RAW_CAPS)
    bad["models"][0][field] = value
    rejects(lambda: images.parse_capabilities(bad))
for field, expected in (("enabled", "IMAGE_MODEL_DISABLED"), ("credential_ready", "IMAGE_CREDENTIAL_NOT_READY")):
    bad = copy.deepcopy(RAW_CAPS)
    bad["models"][0][field] = False
    rejects(lambda: images.prepare_invocation(images.parse_capabilities(bad), **OPTIONS), expected)
bad = copy.deepcopy(RAW_CAPS)
bad["enabled"] = False
rejects(lambda: images.prepare_invocation(images.parse_capabilities(bad), **OPTIONS), "IMAGE_GENERATION_UNAVAILABLE")
for change, code in (({"model_id": "not-advertised"}, "IMAGE_MODEL_REQUIRED"),
                     ({"prompt": " "}, "IMAGE_PROMPT_REQUIRED"), ({"ratio": "99:1"}, "IMAGE_OPTION_UNSUPPORTED"),
                     ({"output_format": "mov"}, "IMAGE_OPTION_UNSUPPORTED"), ({"task": "image-to-image"}, "INVALID_REFERENCE")):
    rejects(lambda: images.prepare_invocation(CAPS, **(OPTIONS | change)), code)

for image_format, mime in (("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
    value = images.validate_image_bytes(image_bytes(image_format), advertised_mime=mime)
    check((value.mime_type, value.width, value.height) == (mime, 13, 7))
rejects(lambda: images.validate_image_bytes(PNG, advertised_mime="image/jpeg"), "INVALID_IMAGE")
rejects(lambda: images.validate_image_bytes(PNG, advertised_sha256="f" * 64), "INVALID_IMAGE")
check(images.validate_image_bytes(PNG, advertised_sha256=hashlib.sha256(PNG).hexdigest().upper()).data == PNG)
rejects(lambda: images.validate_image_bytes(PNG[:30]), "INVALID_IMAGE")
rejects(lambda: images.validate_image_bytes(b"<html>error</html>"), "INVALID_IMAGE")
rejects(lambda: images.validate_image_bytes(PNG, max_bytes=len(PNG) - 1), "IMAGE_LIMIT")
with mock.patch.object(images, "MAX_IMAGE_PIXELS", 10):
    rejects(lambda: images.validate_image_bytes(PNG), "INVALID_IMAGE")

with tempfile.TemporaryDirectory(prefix="hmb-image-protocol-") as temporary:
    folder = Path(temporary)
    reference = folder / "reference.png"
    reference.write_bytes(PNG)
    invocation = images.prepare_invocation(CAPS, **(OPTIONS | {"task": "image-to-image"}),
        references=[reference, SimpleNamespace(value=PNG), {"path": str(reference)}])
    check(len(invocation.payload()["reference_images"]) == 3)
    check(all(item.startswith("data:image/png;base64,") for item in invocation.payload()["reference_images"]))
    canonical_ref = invocation.payload()["reference_images"][0]
    check(images.prepare_invocation(CAPS, **(OPTIONS | {"task": "image-to-image"}),
        references=[canonical_ref]).payload()["reference_images"] == [canonical_ref])
    for reference_value in ("https://external.invalid/reference.png", "file:///private/image.png", "data:image/png;base64,***",
                            {"url": canonical_ref, "path": str(reference)}):
        rejects(lambda: images.prepare_invocation(CAPS, **(OPTIONS | {"task": "image-to-image"}),
            references=[reference_value]), "INVALID_REFERENCE")
    rejects(lambda: images.prepare_invocation(CAPS, **OPTIONS, references=[PNG]), "INVALID_REFERENCE")
    rejects(lambda: images.prepare_invocation(CAPS, **(OPTIONS | {"task": "image-to-image"}), references=[PNG] * 4), "IMAGE_LIMIT")
    bad = copy.deepcopy(RAW_CAPS)
    bad["models"][0]["max_reference_bytes"] = len(PNG) * 2 - 1
    rejects(lambda: images.prepare_invocation(images.parse_capabilities(bad), **(OPTIONS | {"task": "image-to-image"}),
        references=[PNG, PNG]), "IMAGE_LIMIT")
    validated = images.validate_image_bytes(PNG)
    output = folder / "result.jpg"
    original = images.save_image_atomic(validated, output)
    check(original.path.suffix == ".png", "PNG output was mislabeled JPEG")
    check(original.path.read_bytes() == PNG)
    with ThreadPoolExecutor(max_workers=5) as executor:
        saved = list(executor.map(lambda _: images.save_image_atomic(validated, output), range(10)))
    check(len({item.path for item in saved}) == 10, "Concurrent saves overwrote another result")
    check(all(item.path.read_bytes() == PNG for item in saved))
    check(original.path.read_bytes() == PNG)
    rejects(lambda: images.save_image_atomic(validated, folder / "cancelled.png", is_alive=lambda: False), "IMAGE_CANCELLED")
    check(not (folder / "cancelled.png").exists())
    check(not list(folder.glob("*.tmp")))
    with mock.patch.object(images.Path, "unlink", side_effect=OSError("temporary scan lock")):
        preserved = images.save_image_atomic(validated, folder / "preserved.png")
    check(preserved.path.read_bytes() == PNG, "Optional cleanup demoted the completed save")


def job_for(invocation=INVOCATION, status="queued"):
    return {"schema": images.JOB_SCHEMA, "version": 1, "job_id": "job-image-one", "status": status,
            "provider": invocation.provider, "model": invocation.model_id,
            "persistence_scope": "personal_local", "publish_to_reviews": False,
            "client_request_id": invocation.client_request_id,
            **({"result": {"url": "https://broker.example/gateway/api/assets/" + "a" * 43,
                           "mime_type": "image/png", "sha256": hashlib.sha256(PNG).hexdigest()}}
               if status == "succeeded" else {})}


class FakeResponse:
    def __init__(self, url, content=PNG):
        self.url, self.content = url, content
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def geturl(self):
        return self.url
    def read(self, count):
        return self.content[:count]


class FakeBridge:
    server_url = "https://broker.example/gateway"
    def __init__(self):
        self.calls = []
        self.result = job_for()
        self.error = None
        self.capability_error = None
        self.capabilities_result = copy.deepcopy(RAW_CAPS)
        self._opener = SimpleNamespace(open=self.open)
        self.downloads = []
        self.response_url = ""
    def account_snapshot(self, *, connect):
        return SimpleNamespace(connected=True, state="connected", account="test")
    def _load_access_token(self):
        return "test-token-not-provider-key"
    def _request_json(self, method, path, **kwargs):
        self.calls.append((method, path, copy.deepcopy(kwargs)))
        if path.endswith("/capabilities"):
            if self.capability_error:
                raise self.capability_error
            return copy.deepcopy(self.capabilities_result)
        if self.error:
            raise self.error
        return copy.deepcopy(self.result)
    def open(self, request, timeout):
        self.downloads.append(request)
        return FakeResponse(self.response_url or request.full_url)


bridge = FakeBridge()
transport = images.ImageGenerationBroker(bridge)
check(not bridge.calls, "Constructing an image transport made a network call")
rejects(lambda: transport.create(INVOCATION), "IMAGE_GENERATION_UNAVAILABLE")
check(not bridge.calls)
for http_status, code in ((404, "IMAGE_GENERATION_UNSUPPORTED"), (405, "IMAGE_GENERATION_UNSUPPORTED"),
                          (501, "IMAGE_GENERATION_UNSUPPORTED"), (401, "IMAGE_BROKER_LOGIN_REQUIRED"),
                          (502, "IMAGE_BROKER_UNAVAILABLE")):
    error = RuntimeError("provider-secret-error-body-must-not-escape")
    error.status_code = http_status
    bridge.capability_error = error
    denied = rejects(lambda: transport.capabilities(), code)
    check("provider-secret" not in str(denied))
    check(not any(call[1] == "/api/v1/generate/image" for call in bridge.calls))
bridge.capability_error = None
bridge.calls.clear()
AuthFailure = type("_BrokerAuthenticationError", (RuntimeError,), {"__module__": "HMBSeedanceGeneration"})
for error in (AuthFailure("missing secret token body"), AuthFailure("undecryptable secret token body")):
    bridge.capability_error = error
    denied = rejects(lambda: transport.capabilities(), "IMAGE_BROKER_LOGIN_REQUIRED")
    check("secret" not in str(denied) and "login" in str(denied).lower())
bridge.capability_error = RuntimeError("synthetic TLS network error")
denied = rejects(lambda: transport.capabilities(), "IMAGE_BROKER_UNAVAILABLE")
check("login" not in str(denied).lower())
bridge.capability_error = None
bridge.calls.clear()
transport.capabilities()
check(bridge.calls[0][1] == "/api/v1/image-generation/capabilities")
prepared = []
result = transport.create(INVOCATION, on_submission_prepared=lambda invocation: prepared.append(invocation.client_request_id))
check(result["job_id"] == "job-image-one")
check(prepared == [INVOCATION.client_request_id])
create_calls = [call for call in bridge.calls if call[1] == "/api/v1/generate/image"]
check(len(create_calls) == 1)
check(create_calls[0][2]["idempotency_key"] == INVOCATION.client_request_id)
check(create_calls[0][2]["payload"] == INVOCATION.payload())
check("api_key" not in json.dumps(create_calls[0][2]).lower())
check(create_calls[0][2]["payload"]["publish_to_reviews"] is False)
check(create_calls[0][2]["payload"]["persistence_scope"] == "personal_local")
check(not {"project_id", "project_name", "shot", "shot_name", "title"} & set(create_calls[0][2]["payload"]))
check(transport.refresh("job-image-one", invocation=INVOCATION)["job_id"] == "job-image-one")
check(transport.refresh(INVOCATION.client_request_id, client_request_id=INVOCATION.client_request_id,
    invocation=INVOCATION)["job_id"] == "job-image-one")
for error in (AuthFailure("private expired token"), RuntimeError("private connection detail")):
    bridge.error = error
    denied = rejects(lambda: transport.refresh("job-image-one", client_request_id=INVOCATION.client_request_id),
                     "IMAGE_BROKER_LOGIN_REQUIRED" if isinstance(error, AuthFailure) else "IMAGE_STATUS_UNAVAILABLE")
    check("private" not in str(denied) and "job-image-one" in str(denied) and "same Task" in str(denied))
bridge.error = None
check(len([call for call in bridge.calls if call[1] == "/api/v1/generate/image"]) == 1,
      "A status/auth failure resubmitted the create request")
for code, phrase in (("image_model_not_allowed", "model"), ("image_credentials_not_ready", "credential"),
                     ("image_provider_rejected", "provider"), ("image_storage_unavailable", "storage")):
    job = job_for(status="failed")
    job["error"] = {"code": code, "message": "private secret provider body"}
    guidance = images.image_job_failure_message(job)
    check(phrase in guidance.lower() and "private" not in guidance and "secret" not in guidance)
for unsafe in ({"code": "private secret"}, {"message": "private secret"}, "private secret", None):
    check(images.image_job_failure_message({"error": unsafe}) == "")
for key, bad_value in (("job_id", "job-other"), ("provider", "other-provider"), ("model", "other-model"),
                       ("client_request_id", "img-other")):
    bad = job_for()
    bad[key] = bad_value
    rejects(lambda: images.validate_job(bad, expected_job_id="job-image-one", invocation=INVOCATION), "IMAGE_IDENTITY_MISMATCH")
for field, value in (("persistence_scope", "web_reviews"), ("publish_to_reviews", True)):
    bad = job_for()
    bad[field] = value
    rejects(lambda: images.validate_job(bad))
for status in images.JOB_FAILURE_STATUSES | images.JOB_PENDING_STATUSES | images.JOB_SUCCESS_STATUSES:
    check(images.validate_job(job_for(status=status))["status"] == status)
# A running durable job can explicitly carry an unknown provider submission.
# Preserve those fields for the node lifecycle; do not convert it to failure or
# discard recovery identity inside the provider-neutral protocol parser.
running_unknown = job_for(status="running")
running_unknown.update(submission_outcome_unknown=True, error={"code": "image_submission_unknown"})
parsed_unknown = images.validate_job(running_unknown, invocation=INVOCATION)
check(parsed_unknown["submission_outcome_unknown"] is True)
check(parsed_unknown["error"]["code"] == "image_submission_unknown")
parsed_unknown["error"]["code"] = "mutated-local-copy"
check(running_unknown["error"]["code"] == "image_submission_unknown")
bridge.result = running_unknown
check(transport.create(INVOCATION)["submission_outcome_unknown"] is True)
check(transport.refresh("job-image-one", invocation=INVOCATION)["error"]["code"] == "image_submission_unknown")
bridge.result = job_for()
bad = job_for(status="succeeded")
bad["result"] = {"url": "https://broker.example/a", "mime_type": "video/mp4"}
rejects(lambda: images.validate_job(bad))

# Unknown submissions retain their one durable UUID and never automatically POST again.
bridge.error = TimeoutError("simulated transport loss")
before = len(bridge.calls)
unknown = rejects(lambda: transport.create(INVOCATION), "IMAGE_SUBMISSION_UNKNOWN")
check(unknown.submission_outcome_unknown)
check(len(bridge.calls) == before + 1, "Ambiguous image submission was retried")
bridge.error = None
bridge.result = {"status": "accepted-but-invalid-contract"}
unknown = rejects(lambda: transport.create(INVOCATION))
check(unknown.submission_outcome_unknown)
bridge.result = job_for()
before = len(bridge.calls)
rejects(lambda: transport.create(INVOCATION, is_alive=lambda: False), "IMAGE_CANCELLED")
check(len(bridge.calls) == before)
alive = [True]
rejects(lambda: transport.create(INVOCATION, on_submission_prepared=lambda _: alive.__setitem__(0, False),
    is_alive=lambda: alive[0]), "IMAGE_CANCELLED")
check(len(bridge.calls) == before)

with tempfile.TemporaryDirectory(prefix="hmb-image-results-") as temporary:
    output = Path(temporary) / "render.png"
    job = job_for(status="succeeded")
    saved = transport.save_result(job, output)
    check(saved.path.read_bytes() == PNG)
    check(bridge.downloads[-1].get_header("Authorization") == "Bearer test-token-not-provider-key")
    check(bridge.downloads[-1].full_url.startswith(bridge.server_url + "/api/assets/"))
    for url in ("https://evil.example/api/assets/" + "a" * 43,
                "https://broker.example/api/assets/" + "a" * 43,
                "https://broker.example/gateway/api/assets/" + "a" * 43 + "?token=leak",
                "https://user@broker.example/gateway/api/assets/" + "a" * 43):
        bad = copy.deepcopy(job)
        bad["result"]["url"] = url
        before = len(bridge.downloads)
        rejects(lambda: transport.save_result(bad, output), "IMAGE_RESULT_UNTRUSTED")
        check(len(bridge.downloads) == before, "Authentication was sent to an untrusted image URL")
    bridge.response_url = "https://other.example/image.png"
    rejects(lambda: transport.save_result(job, output), "IMAGE_RESULT_UNTRUSTED")
    bridge.response_url = ""
    bad = copy.deepcopy(job)
    bad["result"]["sha256"] = "0" * 64
    rejects(lambda: transport.save_result(bad, output), "INVALID_IMAGE")
    check(saved.path.read_bytes() == PNG)
    rejects(lambda: transport.save_result(job_for(), output), "IMAGE_RESULT_NOT_READY")
    rejects(lambda: transport.save_result(job, output, is_alive=lambda: False), "IMAGE_CANCELLED")

# Additive model-specific options: old capabilities and wire bodies stay intact.
OPTION_DESCRIPTORS = {
    "temperature": {"type": "number", "label": "Temperature", "default": 1.0, "minimum": 0, "maximum": 2, "step": 0.1},
    "top_p": {"type": "number", "label": "Top P", "default": 0.95, "minimum": 0, "maximum": 1, "step": 0.05},
    "use_google_search": {"type": "boolean", "label": "Google Search", "default": False},
    "iterations": {"type": "integer", "label": "Iterations", "default": 0, "minimum": 0, "maximum": 10, "step": 1},
    "style": {"type": "string", "label": "Style", "default": "natural", "enum": ["natural", "graphic"]},
    "note": {"type": "string", "label": "Note", "default": "", "max_length": 32},
}
OPTION_SCHEMA = {"schema": images.OPTION_SCHEMA, "revision": "fixture-options-v1", "properties": OPTION_DESCRIPTORS}
typed_raw = copy.deepcopy(RAW_CAPS)
typed_raw["max_request_bytes"] = 20_000_000
typed_raw["models"][0]["option_schema"] = copy.deepcopy(OPTION_SCHEMA)
typed_raw["models"][0]["defaults"] = {"task": "text-to-image", "ratio": "16:9", "image_size": "1K", "output_format": "png"}
typed_caps = images.parse_capabilities(typed_raw)
typed_model = typed_caps.models[0]
check(typed_caps.max_request_bytes == 20_000_000)
check(CAPS.max_request_bytes == images.MAX_REQUEST_BYTES)
check(images.model_defaults(typed_model)["ratio"] == "16:9")
defaults = images.model_defaults(typed_model)
defaults["ratio"] = "edited"
check(images.model_defaults(typed_model)["ratio"] == "16:9", "Model defaults were mutable through a caller")
revision, specs = images.parse_option_schema(OPTION_SCHEMA)
check(images.serialize_option_schema(revision, specs) == OPTION_SCHEMA)
for name, descriptor in OPTION_DESCRIPTORS.items():
    spec = images.parse_option_spec(name, descriptor)
    check(images.serialize_option_spec(spec) == descriptor)
try:
    specs[0].default = 0
except FrozenInstanceError:
    checks += 1
else:
    raise AssertionError("A live UI edit mutated a frozen option descriptor")
typed_invocation = images.prepare_invocation(typed_caps, **OPTIONS)
check(typed_invocation.payload()["model_options_schema_revision"] == revision)
check(typed_invocation.payload()["model_options"] == {name: descriptor["default"] for name, descriptor in OPTION_DESCRIPTORS.items()})
custom = images.prepare_invocation(typed_caps, **OPTIONS, model_options={"temperature": 0, "use_google_search": False,
    "iterations": 0, "style": "graphic", "note": ""})
check(custom.payload()["model_options"]["temperature"] == 0)
check(type(custom.payload()["model_options"]["use_google_search"]) is bool)
check(custom.payload()["model_options"]["iterations"] == 0)
for invalid in ({"temperature": True}, {"temperature": "1.0"}, {"temperature": float("nan")},
                {"temperature": float("inf")}, {"temperature": 2.1}, {"temperature": 0.15},
                {"top_p": -0.05}, {"use_google_search": 0}, {"use_google_search": "false"},
                {"iterations": False}, {"iterations": 1.0}, {"iterations": 11}, {"style": "unknown"},
                {"note": "x" * 33}, {"note": "\x00"}, {"unknown_future_option": 1}):
    rejects(lambda: images.prepare_invocation(typed_caps, **OPTIONS, model_options=invalid))
rejects(lambda: images.prepare_invocation(CAPS, **OPTIONS, model_options={"temperature": 1.0}), "IMAGE_OPTION_UNSUPPORTED")
legacy = images.prepare_invocation(CAPS, **OPTIONS, model_options={})
check(len(legacy.payload()) == 11)
check("model_options" not in legacy.payload() and "model_options_schema_revision" not in legacy.payload())
for bad_descriptor in (
    {"type": "object", "label": "Future", "default": {}},
    {"type": ["number"], "default": 0},
    {"type": "boolean", "default": 0},
    {"type": "number", "default": float("nan")},
    {"type": "number", "default": 0, "step": 0},
    {"type": "number", "default": 0, "minimum": 2, "maximum": 1},
    {"type": "integer", "default": 0, "step": 0.5},
    {"type": "string", "default": "a", "enum": ["a", "a"]},
    {"type": "string", "default": "a", "enum": []},
    {"type": "string", "default": "a", "enum": ["a"] * 65},
    {"type": "string", "default": "a", "max_length": True},
    {"type": "string", "default": "a", "unknown_rule": "passthrough"},
):
    rejects(lambda: images.parse_option_spec("option", bad_descriptor))
too_many_options = copy.deepcopy(OPTION_SCHEMA)
too_many_options["properties"] = {f"option_{i}": {"type": "boolean", "default": False} for i in range(33)}
rejects(lambda: images.parse_option_schema(too_many_options), "IMAGE_OPTION_SCHEMA_INVALID")
for invalid_limit in (True, 0, -1, 1.5, 2**31):
    bad = copy.deepcopy(RAW_CAPS)
    bad["max_request_bytes"] = invalid_limit
    rejects(lambda: images.parse_capabilities(bad))
bad_defaults = copy.deepcopy(typed_raw)
bad_defaults["models"][0]["defaults"]["image_size"] = "unsupported-size"
rejects(lambda: images.parse_capabilities(bad_defaults))

pro, banana2 = images.BUILTIN_IMAGE_MODEL_PROFILES
check(pro.model_id == "gemini-3-pro-image" and banana2.model_id == "gemini-3.1-flash-image")
check(pro.image_sizes == ("1K", "2K", "4K") and banana2.image_sizes == ("512", "1K", "2K", "4K"))
check(len(pro.aspect_ratios) == 10 and len(banana2.aspect_ratios) == 14)
check("use_google_image_search" not in {item.name for item in pro.options})
check("use_google_image_search" in {item.name for item in banana2.options})
check(not any(item.enabled or item.credential_ready for item in (pro, banana2)))
rejects(lambda: images.prepare_invocation(images.ImageCapabilities(True, (pro,)),
    **(OPTIONS | {"model_id": pro.model_id}), model_options={}), "IMAGE_MODEL_DISABLED")
actual_pro_fixture = replace(pro, enabled=True, credential_ready=True)
rejects(lambda: images.prepare_invocation(images.ImageCapabilities(True, (actual_pro_fixture,)),
    **(OPTIONS | {"model_id": pro.model_id}), model_options={"use_google_image_search": False}), "IMAGE_OPTION_UNSUPPORTED")

typed_bridge = FakeBridge()
typed_bridge.capabilities_result = typed_raw
typed_transport = images.ImageGenerationBroker(typed_bridge)
typed_transport.capabilities()
typed_bridge.result = job_for(custom)
typed_transport.create(custom)
check(typed_bridge.calls[-1][2]["payload"]["model_options"]["temperature"] == 0)
check(typed_bridge.calls[-1][2]["payload"]["model_options_schema_revision"] == revision)
typed_transport._capabilities = replace(typed_caps, models=(replace(typed_model, option_schema_revision="new-revision"),))
before = len(typed_bridge.calls)
rejects(lambda: typed_transport.create(custom), "IMAGE_IDENTITY_MISMATCH")
check(len(typed_bridge.calls) == before, "A stale option schema crossed the billable boundary")

# Auto resize is local-only and opt-in to the helper. It changes bytes only
# when a real model or encoded-request byte limit would otherwise reject them.
with tempfile.TemporaryDirectory(prefix="hmb-image-auto-resize-") as temporary:
    reference = Path(temporary) / "unchanged-original.png"
    original_image = Image.frombytes("RGB", (512, 256), random.Random(73).randbytes(512 * 256 * 3))
    stream = io.BytesIO()
    original_image.save(stream, "PNG")
    noise = stream.getvalue()
    reference.write_bytes(noise)
    before = (reference.read_bytes(), reference.stat().st_mtime_ns)
    small_budget_model = replace(CAPS.models[0], max_reference_bytes=12000)
    small_budget = replace(CAPS, models=(small_budget_model,))
    edit_options = OPTIONS | {"task": "image-to-image"}
    rejects(lambda: images.prepare_invocation(small_budget, **edit_options, references=[reference]), "IMAGE_LIMIT")
    resized = images.prepare_invocation(small_budget, **edit_options, references=[reference], auto_image_resize=True)
    resized_data = base64.b64decode(resized.payload()["reference_images"][0].split(",", 1)[1])
    resized_image = images.validate_image_bytes(resized_data)
    check(len(resized_data) <= small_budget_model.max_reference_bytes)
    check(resized_image.width < 512 and resized_image.height < 256)
    check(abs(resized_image.width * 256 - resized_image.height * 512) <= 512, "Auto resize stretched the reference")
    check((reference.read_bytes(), reference.stat().st_mtime_ns) == before, "Auto resize overwrote an original reference")
    check("auto_image_resize" not in resized.payload())
    unchanged = images.prepare_invocation(CAPS, **edit_options, references=[reference], auto_image_resize=True)
    check(base64.b64decode(unchanged.payload()["reference_images"][0].split(",", 1)[1]) == noise)
    paired_model = replace(CAPS.models[0], max_reference_bytes=20000)
    paired = images.prepare_invocation(replace(CAPS, models=(paired_model,)), **edit_options,
        references=[reference, reference], auto_image_resize=True)
    check(sum(len(base64.b64decode(value.split(",", 1)[1])) for value in paired.payload()["reference_images"]) <= 20000)
    request_budget = replace(CAPS, max_request_bytes=14000)
    rejects(lambda: images.prepare_invocation(request_budget, **edit_options, references=[reference]), "IMAGE_LIMIT")
    request_fit = images.prepare_invocation(request_budget, **edit_options, references=[reference], auto_image_resize=True)
    check(len(json.dumps(request_fit.payload(), ensure_ascii=False, separators=(",", ":")).encode()) <= 14000)
    for image_format, mime in (("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
        encoded = io.BytesIO()
        original_image.save(encoded, image_format, quality=100)
        encoded_original = encoded.getvalue()
        format_fit = images.prepare_invocation(small_budget, **edit_options, references=[encoded_original], auto_image_resize=True)
        format_data = base64.b64decode(format_fit.payload()["reference_images"][0].split(",", 1)[1])
        format_image = images.validate_image_bytes(format_data, advertised_mime=mime)
        check(len(format_data) <= 12000)
        check(format_image.width <= 512 and format_image.height <= 256)
        check(abs(format_image.width * 256 - format_image.height * 512) <= 512)
    impossible = replace(CAPS, models=(replace(CAPS.models[0], max_reference_bytes=20),))
    rejects(lambda: images.prepare_invocation(impossible, **edit_options, references=[reference], auto_image_resize=True), "IMAGE_LIMIT")
    rejects(lambda: images.prepare_invocation(CAPS, **OPTIONS, auto_image_resize="true"), "IMAGE_OPTION_INVALID")
    rejects(lambda: images.prepare_invocation(replace(CAPS, max_request_bytes=32), **OPTIONS), "IMAGE_LIMIT")

# New clients negotiate the additive contract; historical PNG requests keep
# their exact shape. Verify the real helper create revalidation as well.
native_raw = copy.deepcopy(RAW_CAPS)
native_model = native_raw["models"][0]
native_model.update(provider="google", model_id="gemini-3.1-flash-image", max_reference_images=14,
    provider_request_contract=images.GOOGLE_NATIVE_CONTRACT)
native_model["native_contract"] = {
    "output_formats": ["native"],
    "defaults": {"task": "text-to-image", "ratio": "16:9", "image_size": "1K", "output_format": "native"},
    "option_schema": images.serialize_option_schema("native-parity-fixture-v1", images.BUILTIN_IMAGE_MODEL_PROFILES[1].options),
    "max_reference_image_bytes": 7 * 1024 * 1024, "max_reference_bytes": 14900000, "max_result_images": 32}
native_caps = images.parse_capabilities(native_raw)
native_options = OPTIONS | {"provider": "google", "model_id": "gemini-3.1-flash-image", "output_format": "native",
    "provider_request_contract": images.GOOGLE_NATIVE_CONTRACT,
    "model_options": {"temperature": 0.0, "top_p": 0.0, "use_google_search": True, "use_google_image_search": True}}
native_invocation = images.prepare_invocation(native_caps, **native_options)
check(native_invocation.payload()["output_format"] == "native")
check(native_invocation.payload()["model_options"]["use_google_image_search"] is True)
check(native_model["output_formats"] == ["png", "jpeg", "webp"], "Native overlay mutated legacy capabilities")
old_google = copy.deepcopy(native_raw)
old_google["models"][0].pop("provider_request_contract")
old_google["models"][0].pop("native_contract")
rejects(lambda: images.prepare_invocation(images.parse_capabilities(old_google), **native_options), "IMAGE_NATIVE_CONTRACT_REQUIRED")
rejects(lambda: images.prepare_invocation(native_caps, **(native_options | {"provider_request_contract": ""})), "IMAGE_NATIVE_CONTRACT_REQUIRED")
for bad_value in (None, {}, {"output_formats": ["png"]}):
    bad = copy.deepcopy(native_raw)
    bad["models"][0]["native_contract"] = bad_value
    rejects(lambda: images.parse_capabilities(bad))

native_bridge = FakeBridge()
native_bridge.capabilities_result = native_raw
native_transport = images.ImageGenerationBroker(native_bridge)
native_transport.capabilities()
native_job = job_for(native_invocation, status="succeeded")
native_job["provider_request_contract"] = images.GOOGLE_NATIVE_CONTRACT
native_job["results"] = [copy.deepcopy(native_job["result"])]
originals = [PNG, image_bytes("JPEG"), image_bytes("WEBP")]
for index, mime in ((1, "image/jpeg"), (2, "image/webp")):
    native_job["results"].append({"url": native_bridge.server_url + "/api/assets/" + chr(97 + index) * 43,
        "mime_type": mime, "sha256": hashlib.sha256(originals[index]).hexdigest()})
native_job["text"] = "literal generated text <plain>"
native_bridge.result = native_job
check(native_transport.create(native_invocation)["results"] == native_job["results"])
check(native_bridge.calls[-1][2]["payload"] == native_invocation.payload())
bad = copy.deepcopy(native_job)
bad.pop("provider_request_contract")
rejects(lambda: images.validate_job(bad, invocation=native_invocation), "IMAGE_IDENTITY_MISMATCH")
for mutation in (lambda j: j["results"].reverse(), lambda j: j["results"][1].pop("sha256"),
                 lambda j: j["results"].append(j["results"][0]), lambda j: j.update(text="x" * 65537)):
    bad = copy.deepcopy(native_job)
    mutation(bad)
    rejects(lambda: images.validate_job(bad, invocation=native_invocation))
with tempfile.TemporaryDirectory(prefix="hmb-native-images-") as folder:
    for index, raw in enumerate(originals):
        with mock.patch.object(native_bridge._opener, "open",
                side_effect=lambda request, timeout, raw=raw: FakeResponse(request.full_url, raw)):
            saved = native_transport.save_result(native_job, Path(folder) / "image.png", result_index=index)
        check(saved.path.read_bytes() == raw)
        check(saved.path.suffix == (".png", ".jpg", ".webp")[index])
    rejects(lambda: native_transport.save_result(native_job, Path(folder) / "image.png", result_index=3), "IMAGE_IDENTITY_MISMATCH")
    before = len(native_bridge.downloads)
    bad = copy.deepcopy(native_job)
    bad["results"][1]["url"] = "https://other.invalid/api/assets/" + "z" * 43
    rejects(lambda: native_transport.save_result(bad, Path(folder) / "image.png", result_index=1), "IMAGE_RESULT_UNTRUSTED")
    check(len(native_bridge.downloads) == before)

# Native reference count/order and WebP compression match the installed
# Standard strategy. Direct Broker request budget is additionally enforced.
edit_native = native_options | {"task": "image-to-image"}
many = images.prepare_invocation(native_caps, **edit_native, references=[PNG] * 14)
check(len(many.payload()["reference_images"]) == 14)
rejects(lambda: images.prepare_invocation(native_caps, **edit_native, references=[PNG] * 15), "IMAGE_LIMIT")
small_native = replace(native_caps, models=(replace(native_caps.models[0], max_reference_image_bytes=100),))
rejects(lambda: images.prepare_invocation(small_native, **edit_native, references=[image_bytes(size=(100, 60))]), "IMAGE_LIMIT")
shrunk = images.prepare_invocation(small_native, **edit_native, references=[image_bytes(size=(100, 60))], auto_image_resize=True)
check(shrunk.payload()["reference_images"][0].startswith("data:image/webp;base64,"))
check(len(base64.b64decode(shrunk.payload()["reference_images"][0].split(",", 1)[1])) <= 100)
print(json.dumps({"status": "PASS", "checks": checks, "network": "mock-only", "paid_generation": False}))
