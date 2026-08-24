from __future__ import annotations

"""Seedance media memory/preflight regression for v0.6.46 local testing."""

import base64
import importlib.util
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

    def fake_request(method, url, *, content, headers, timeout):
        chunks = list(content)
        captured.update(
            method=method,
            url=url,
            chunks=chunks,
            headers=dict(headers),
            timeout=timeout,
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

print("HMB Seedance media preflight/streaming regression: PASS")
