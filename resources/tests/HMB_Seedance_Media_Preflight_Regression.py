from __future__ import annotations

"""Seedance media memory/preflight regression for v0.6.46 local testing."""

import base64
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs


install_clean_ci_griptape_stubs()


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "HMBSeedanceGeneration.py"
SPEC = importlib.util.spec_from_file_location(
    "hmb_seedance_media_preflight_regression",
    TARGET,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load regression target: {TARGET}")
seedance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = seedance
SPEC.loader.exec_module(seedance)

assert callable(
    getattr(seedance.GriptapeCloudStorageDriver, "create_signed_upload_url", None)
)
assert callable(
    getattr(seedance.GriptapeCloudStorageDriver, "create_signed_download_url", None)
)


with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)

    # Chunk boundaries must remain Base64-canonical even when the final block
    # is not divisible by three.
    media = (bytes(range(256)) * 5000) + b"tail!"
    media_path = folder / "reference.wav"
    media_path.write_bytes(media)
    data_uri = seedance.HMBSeedanceGeneration._encode_local_media_data_uri(
        media_path,
        "audio/wav",
    )
    assert data_uri.startswith("data:audio/wav;base64,")
    assert base64.b64decode(data_uri.split(",", 1)[1], validate=True) == media

    # Two individually valid images exceed the request envelope together. The
    # projection rejects them from stat data before either file is read/Base64'd.
    image_a = folder / "large-a.png"
    image_b = folder / "large-b.png"
    with image_a.open("wb") as stream:
        stream.truncate(29 * 1024 * 1024)
    with image_b.open("wb") as stream:
        stream.truncate(20 * 1024 * 1024)
    try:
        seedance.HMBSeedanceGeneration._preflight_broker_media_size(
            {"prompt": "bounded preflight"},
            (("image_urls", "image", [str(image_a), str(image_b)]),),
        )
    except ValueError as exc:
        assert "64 MB" in str(exc)
    else:
        raise AssertionError("Oversized cumulative media passed the early preflight")

    # Current Griptape hosts expose signed URL methods. Verify that the upload
    # consumes bounded chunks and never asks the compatibility bytes API.
    upload_media = (b"0123456789abcdef" * 140_000) + b"end"
    upload_path = folder / "streamed-reference.mp4"
    upload_path.write_bytes(upload_media)

    class SignedDriver:
        def __init__(self) -> None:
            self.upload_file_called = False

        def create_signed_upload_url(self, path: Path):
            assert path == Path("artifact_url_storage/probe/reference.mp4")
            return {
                "method": "PUT",
                "url": "https://storage.example/signed-upload",
                "headers": {"x-upload-token": "opaque"},
            }

        def create_signed_download_url(self, path: Path):
            assert path == Path("artifact_url_storage/probe/reference.mp4")
            return "https://storage.example/signed-download"

        def upload_file(self, **_kwargs):
            self.upload_file_called = True
            raise AssertionError("Streaming host fell back to whole-file upload")

    captured: dict = {}
    original_request = seedance.httpx.request

    def fake_request(
        method,
        url,
        *,
        content,
        headers,
        timeout,
        follow_redirects,
        trust_env,
    ):
        chunks = list(content)
        captured.update(
            method=method,
            url=url,
            chunks=chunks,
            headers=dict(headers),
            timeout=timeout,
            follow_redirects=follow_redirects,
            trust_env=trust_env,
        )
        return SimpleNamespace(raise_for_status=lambda: None)

    driver = SignedDriver()
    node = object.__new__(seedance.HMBSeedanceGeneration)
    remote_path = Path("artifact_url_storage/probe/reference.mp4")
    seedance.httpx.request = fake_request
    try:
        public_url = node._upload_local_video_to_griptape_cloud(
            driver,
            upload_path,
            remote_path,
        )
    finally:
        seedance.httpx.request = original_request

    assert public_url == "https://storage.example/signed-download"
    assert driver.upload_file_called is False
    assert b"".join(captured["chunks"]) == upload_media
    assert max(map(len, captured["chunks"])) <= seedance.CLOUD_UPLOAD_READ_CHUNK_BYTES
    assert captured["headers"]["Content-Length"] == str(len(upload_media))
    assert captured["timeout"] == 120.0
    assert captured["follow_redirects"] is False
    assert captured["trust_env"] is False

    # httpx includes a full request URL in status exceptions. Signed Cloud/TOS
    # query credentials must never reach the node's public error/status output.
    signed_query_url = (
        "https://storage.example/private-upload.png?"
        "X-Amz-Credential=TEST_CREDENTIAL_MARKER&"
        "X-Amz-Signature=TEST_SIGNATURE_MARKER"
    )
    signed_request = seedance.httpx.Request("PUT", signed_query_url)
    signed_response = seedance.httpx.Response(
        403,
        request=signed_request,
    )
    try:
        signed_response.raise_for_status()
    except seedance.httpx.HTTPStatusError as exc:
        safe_error = seedance.HMBSeedanceGeneration._safe_exception_message(exc)
    else:
        raise AssertionError("Expected signed-upload HTTP status failure")
    assert "TEST_CREDENTIAL_MARKER" not in safe_error
    assert "TEST_SIGNATURE_MARKER" not in safe_error
    assert "https://storage.example/private-upload.png?[REDACTED]" in safe_error

    # One verified Cloud driver is shared by image and video preparation. Local
    # images/data URIs become HTTPS references, while an existing public HTTPS
    # image is preserved byte-for-byte and saved parameter values stay untouched.
    image_path = folder / "cloud-reference.png"
    image_bytes = b"\x89PNG\r\n\x1a\ncloud-reference"
    image_path.write_bytes(image_bytes)
    image_data_uri = (
        "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    )

    class LegacyCloudDriver:
        def __init__(self) -> None:
            self.uploads: list[dict] = []
            self.deletes: list[Path] = []

        def upload_file(self, *, path: Path, file_content: bytes, timeout: float):
            self.uploads.append(
                {
                    "path": path,
                    "file_content": bytes(file_content),
                    "timeout": timeout,
                }
            )
            return f"https://storage.example/{path.name}?signed=opaque"

        def delete_file(self, path: Path) -> None:
            self.deletes.append(path)

    cloud_driver = LegacyCloudDriver()
    cloud_node = object.__new__(seedance.HMBSeedanceGeneration)
    cloud_node.name = "Cloud Media Transport Regression"
    cloud_node._temporary_video_uploads = []
    cloud_node._temporary_tos_video_uploads = []
    cloud_node._try_create_gt_cloud_storage_driver = lambda: cloud_driver
    cloud_params = {
        "first_frame": str(image_path),
        "last_frame": None,
        "reference_images": [
            image_data_uri,
            "https://cdn.example/already-public.png",
        ],
        "video_reference_slots": [str(upload_path)],
        "video_references": [],
        "auto_publish_local_videos": True,
        # A ready Griptape Cloud credential+bucket is the preferred transport
        # for both media kinds; TOS remains the no-Cloud video fallback.
        "local_video_upload_service": seedance.LOCAL_VIDEO_UPLOAD_TOS,
    }
    prepared_cloud = cloud_node._prepare_video_references_for_run(cloud_params)
    assert prepared_cloud["first_frame"].startswith("https://storage.example/")
    assert prepared_cloud["reference_images"][0].startswith(
        "https://storage.example/"
    )
    assert prepared_cloud["reference_images"][1] == (
        "https://cdn.example/already-public.png"
    )
    assert prepared_cloud["video_references"][0].startswith(
        "https://storage.example/"
    )
    assert cloud_params["first_frame"] == str(image_path)
    assert cloud_params["reference_images"][0] == image_data_uri
    assert cloud_params["video_reference_slots"][0] == str(upload_path)
    assert len(cloud_driver.uploads) == 3
    assert len(cloud_node._temporary_video_uploads) == 3

    # Without a usable Cloud credential/bucket, image preparation remains on
    # the existing Base64 JSON path and public video references need no upload.
    fallback_node = object.__new__(seedance.HMBSeedanceGeneration)
    fallback_node.name = "Base64 Image Fallback Regression"
    fallback_node._temporary_video_uploads = []
    fallback_node._temporary_tos_video_uploads = []
    fallback_node._try_create_gt_cloud_storage_driver = lambda: None
    fallback_params = {
        "first_frame": str(image_path),
        "last_frame": None,
        "reference_images": [image_data_uri],
        "video_reference_slots": ["https://cdn.example/reference.mp4"],
        "video_references": [],
        "auto_publish_local_videos": True,
        "local_video_upload_service": seedance.LOCAL_VIDEO_UPLOAD_GRIPTAPE,
    }
    prepared_fallback = fallback_node._prepare_video_references_for_run(
        fallback_params
    )
    assert prepared_fallback["first_frame"] == str(image_path)
    assert prepared_fallback["reference_images"] == [image_data_uri]
    assert prepared_fallback["video_references"] == [
        "https://cdn.example/reference.mp4"
    ]
    encoded_fallback = fallback_node._prepare_media_reference(
        "image",
        prepared_fallback["first_frame"],
    )
    assert encoded_fallback.startswith("data:image/png;base64,")
    assert base64.b64decode(encoded_fallback.split(",", 1)[1]) == image_bytes

    # Local video still cannot use Base64. When Cloud is unavailable, the
    # existing explicitly selected TOS path remains the permitted fallback.
    fallback_node._create_tos_storage_context = lambda _params: ("tos", "client", "bucket")
    fallback_node._upload_local_video_to_tos = (
        lambda _path, _params, _context: "https://tos.example/reference.mp4?signed=opaque"
    )
    tos_params = dict(fallback_params)
    tos_params["first_frame"] = None
    tos_params["reference_images"] = []
    tos_params["video_reference_slots"] = [str(upload_path)]
    tos_params["local_video_upload_service"] = seedance.LOCAL_VIDEO_UPLOAD_TOS
    prepared_tos = fallback_node._prepare_video_references_for_run(tos_params)
    assert prepared_tos["video_references"] == [
        "https://tos.example/reference.mp4?signed=opaque"
    ]

    # Cloud readiness is one atomic credential+accessible-bucket contract.
    # A blank explicit bucket may resolve the account default; missing auth or
    # an inaccessible configured bucket selects the media fallbacks instead.
    class ReadinessSecrets:
        def __init__(self, values: dict[str, str]) -> None:
            self.values = dict(values)

        def get_secret(self, name: str, *, should_error_on_not_found: bool = False):
            del should_error_on_not_found
            return self.values.get(name)

    class ReadinessStorageDriver:
        explicit_accessible = True
        default_bucket = "default-bucket"
        bucket_checks: list[str] = []
        default_calls = 0

        @classmethod
        def bucket_exists(cls, bucket_id: str, **_kwargs):
            cls.bucket_checks.append(bucket_id)
            return cls.explicit_accessible

        @classmethod
        def get_default_bucket_id(cls, **_kwargs):
            cls.default_calls += 1
            return cls.default_bucket

        def __init__(
            self,
            config_manager,
            *,
            bucket_id: str,
            api_key: str | None = None,
            **kwargs,
        ) -> None:
            self.config_manager = config_manager
            self.kwargs = {
                "bucket_id": bucket_id,
                "api_key": api_key,
                **kwargs,
            }

    class LegacyReadinessStorageDriver(ReadinessStorageDriver):
        def __init__(
            self,
            *,
            workspace_directory,
            bucket_id: str,
            api_key: str | None = None,
            **kwargs,
        ) -> None:
            self.workspace_directory = workspace_directory
            self.kwargs = dict(kwargs)
            self.kwargs.update(
                {
                    "bucket_id": bucket_id,
                    "api_key": api_key,
                }
            )

    original_nodes = seedance.GriptapeNodes
    original_driver_class = seedance.GriptapeCloudStorageDriver
    original_resolver = seedance.resolve_cloud_credential
    original_base_url = seedance.os.environ.get("GT_CLOUD_BASE_URL")
    readiness_values = {
        seedance.GT_CLOUD_API_KEY_SECRET: "credential-value",
        seedance.GT_CLOUD_BUCKET_ID_SECRET: "explicit-bucket",
    }
    readiness_secrets = ReadinessSecrets(readiness_values)
    readiness_config_manager = SimpleNamespace(workspace_path=folder)
    seedance.GriptapeNodes = SimpleNamespace(
        SecretsManager=lambda: readiness_secrets,
        ConfigManager=lambda: readiness_config_manager,
    )
    seedance.GriptapeCloudStorageDriver = ReadinessStorageDriver
    seedance.resolve_cloud_credential = (
        lambda manager, *, secret_name: manager.get_secret(
            secret_name,
            should_error_on_not_found=False,
        )
    )
    readiness_node = object.__new__(seedance.HMBSeedanceGeneration)
    readiness_node.name = "Cloud Readiness Regression"
    try:
        seedance.os.environ["GT_CLOUD_BASE_URL"] = "https://cloud.griptape.ai"
        explicit_driver = readiness_node._create_gt_cloud_storage_driver()
        assert explicit_driver.config_manager is readiness_config_manager
        assert explicit_driver.kwargs["bucket_id"] == "explicit-bucket"
        assert explicit_driver.kwargs["api_key"] == "credential-value"
        assert explicit_driver.kwargs["base_url"] == "https://cloud.griptape.ai"
        assert explicit_driver.kwargs["request_timeout"] == 30.0
        assert ReadinessStorageDriver.bucket_checks == ["explicit-bucket"]

        seedance.GriptapeCloudStorageDriver = LegacyReadinessStorageDriver
        legacy_driver = readiness_node._create_gt_cloud_storage_driver()
        assert legacy_driver.workspace_directory == folder
        assert legacy_driver.kwargs["bucket_id"] == "explicit-bucket"
        seedance.GriptapeCloudStorageDriver = ReadinessStorageDriver

        readiness_values.pop(seedance.GT_CLOUD_BUCKET_ID_SECRET)
        readiness_secrets.values = dict(readiness_values)
        default_driver = readiness_node._create_gt_cloud_storage_driver()
        assert default_driver.kwargs["bucket_id"] == "default-bucket"
        assert ReadinessStorageDriver.default_calls == 1

        readiness_values.pop(seedance.GT_CLOUD_API_KEY_SECRET)
        readiness_secrets.values = dict(readiness_values)
        assert readiness_node._try_create_gt_cloud_storage_driver() is None

        readiness_values.update(
            {
                seedance.GT_CLOUD_API_KEY_SECRET: "credential-value",
                seedance.GT_CLOUD_BUCKET_ID_SECRET: "inaccessible-bucket",
            }
        )
        readiness_secrets.values = dict(readiness_values)
        ReadinessStorageDriver.explicit_accessible = False
        assert readiness_node._try_create_gt_cloud_storage_driver() is None

        for invalid_url in (
            "http://storage.example/object",
            "https://localhost/object",
            "https://user:password@storage.example/object",
            "https://storage.example/object#fragment",
        ):
            try:
                readiness_node._require_cloud_https_url(
                    invalid_url,
                    label="download",
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError(
                    f"Unsafe Cloud media URL was accepted: {invalid_url}"
                )

        seedance.os.environ["GT_CLOUD_BASE_URL"] = "http://cloud.griptape.ai"
        assert readiness_node._try_create_gt_cloud_storage_driver() is None
    finally:
        seedance.GriptapeNodes = original_nodes
        seedance.GriptapeCloudStorageDriver = original_driver_class
        seedance.resolve_cloud_credential = original_resolver
        if original_base_url is None:
            seedance.os.environ.pop("GT_CLOUD_BASE_URL", None)
        else:
            seedance.os.environ["GT_CLOUD_BASE_URL"] = original_base_url


# The Broker transport is the single exact JSON serialization/size boundary.
# A request exactly at the limit is sent byte-for-byte, while the next smaller
# limit rejects the same body before the opener (and therefore the network) is
# touched.  This keeps the early media projection without materializing and
# serializing the final Base64 request a second time in the node builder.
transport_payload = {
    "prompt": "single serialization boundary",
    "image_urls": ["data:image/png;base64,QUJDRA=="],
}
expected_transport_body = json.dumps(
    transport_payload,
    ensure_ascii=False,
    separators=(",", ":"),
).encode("utf-8")


class BrokerResponse:
    status = 200

    def __init__(self, url: str) -> None:
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self) -> str:
        return self._url

    def read(self, _limit: int) -> bytes:
        return b'{"status":"accepted"}'


class CapturingOpener:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request, *, timeout: float):
        self.requests.append((request, timeout))
        return BrokerResponse(request.full_url)


original_request_limit = seedance.MAX_REQUEST_BYTES
original_load_token = seedance._broker_load_token
capturing_opener = CapturingOpener()
seedance.MAX_REQUEST_BYTES = len(expected_transport_body)
seedance._broker_load_token = lambda: "regression-token"
try:
    bridge = seedance._HMBAIBrokerBridge(opener=capturing_opener)
    response = bridge._request_json(
        "POST",
        "/api/v1/generate/video",
        payload=transport_payload,
        timeout=3.0,
        submission=True,
    )
    assert response == {"status": "accepted", "_http_status": 200}
    assert len(capturing_opener.requests) == 1
    sent_request, sent_timeout = capturing_opener.requests[0]
    assert sent_request.data == expected_transport_body
    assert sent_timeout == 3.0

    seedance.MAX_REQUEST_BYTES = len(expected_transport_body) - 1
    try:
        bridge._request_json(
            "POST",
            "/api/v1/generate/video",
            payload=transport_payload,
            timeout=3.0,
            submission=True,
        )
    except ValueError as exc:
        assert "64 MB" in str(exc)
    else:
        raise AssertionError("Oversized exact Broker body reached the opener")
    assert len(capturing_opener.requests) == 1
finally:
    seedance.MAX_REQUEST_BYTES = original_request_limit
    seedance._broker_load_token = original_load_token

print("HMB Seedance media preflight/streaming regression: PASS")
