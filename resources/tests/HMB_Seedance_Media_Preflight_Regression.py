from __future__ import annotations

"""Seedance media memory/preflight regression for v0.6.46 local testing."""

import base64
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import wave
from contextlib import nullcontext
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image

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


def expected_proof(content: bytes) -> str:
    return f"#hmb-v1={hashlib.sha256(content).hexdigest()}:{len(content)}"


def check_seedance_reference_upload_copy():
    from _hmb_video_tools import _find_ffmpeg, probe_video

    with tempfile.TemporaryDirectory() as directory:
        original = Path(directory) / 'source.mp4'
        subprocess.run([_find_ffmpeg(), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=blue:s=640x360:r=24:d=2', '-c:v', 'libx264', '-pix_fmt',
                        'yuv420p', str(original)], check=True, timeout=20)
        original_bytes = original.read_bytes()
        upload_path = seedance.HMBSeedanceGeneration._reference_video_upload_path
        with upload_path(original, seedance.SEEDANCE_2_5_MODEL_ID) as copy:
            assert copy != original and copy.name == original.name
            probed = probe_video(copy)
            assert (probed['width'], probed['height'], probed['frame_rate'], probed['duration']) == (854, 480, 24.0, 2.0)
            transport = object.__new__(seedance.HMBSeedanceGeneration)
            uploaded = []
            def upload_file(*, path, file_content, timeout):
                uploaded.append(file_content)
                return 'https://storage.example/transcoded.mp4?b=%2f&a=2&a=1'
            result = transport._upload_local_video_to_griptape_cloud(
                SimpleNamespace(upload_file=upload_file), copy, Path('probe.mp4'), cloud_proof_v1=True,
            )
            assert uploaded == [copy.read_bytes()] and uploaded[0] != original_bytes
            assert result == 'https://storage.example/transcoded.mp4?b=%2f&a=2&a=1' + expected_proof(uploaded[0])
            with upload_path(copy, seedance.SEEDANCE_2_5_MODEL_ID) as existing:
                assert existing == copy
        assert not copy.exists() and original.read_bytes() == original_bytes
        with upload_path(original, seedance.SEEDANCE_2_0_MODEL_ID) as unchanged:
            assert unchanged == original

        heavy = Path(directory) / "Picker-original.mov"
        subprocess.run([_find_ffmpeg(), "-nostdin", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc2=s=854x480:r=24:d=2",
                        "-vf", "noise=alls=50:allf=t+u", "-c:v", "libx264",
                        "-preset", "ultrafast", "-crf", "0", str(heavy)], check=True, timeout=30)
        source_bytes = heavy.read_bytes()
        assert len(source_bytes) * 8 / 2 > seedance.SEEDANCE_REFERENCE_VIDEO_COPY_THRESHOLD
        with upload_path(heavy, seedance.SEEDANCE_2_5_MODEL_ID) as copy:
            assert copy.suffix == ".mp4" and copy != heavy
            assert copy.stat().st_size < len(source_bytes) / 2
            media = probe_video(copy)
            assert (media["width"], media["height"], media["frame_rate"], media["duration"],
                    media["video_codec"]) == (854, 480, 24.0, 2.0, "h264")
            encoded = copy.read_bytes()
            assert encoded.index(b"moov") < encoded.index(b"mdat")
        assert heavy.read_bytes() == source_bytes and not copy.exists()


check_seedance_reference_upload_copy()


def check_lossless_image_cache_after_overwrite():
    generator = object.__new__(seedance.HMBSeedanceGeneration)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "same-reference.png"
        for color in ("red", "blue"):
            # Uncompressed PNGs of the same dimensions have the same byte length.
            Image.new("RGB", (1024, 768), color).save(path, compress_level=0)
            info = path.stat()
            if color == "blue":
                assert info.st_size == old_stat.st_size
                os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
            result = generator._prepare_cloud_image(str(path), seedance.SEEDANCE_2_5_MODEL_ID, 1)
            data, filename = result
            assert filename == "same-reference.webp"
            with Image.open(BytesIO(data)) as decoded:
                assert decoded.size == (1024, 768)
                assert decoded.getpixel((100, 100)) == ((255, 0, 0) if color == "red" else (0, 0, 255))
            if color == "red":
                old_stat, previous = info, data
            else:
                assert data != previous
            # Re-reading either unchanged revision must reuse its verified packed bytes.
            with mock.patch.object(Image.Image, "save", side_effect=AssertionError("unchanged PNG re-encoded")):
                assert generator._prepare_cloud_image(str(path), seedance.SEEDANCE_2_5_MODEL_ID, 1) == result


check_lossless_image_cache_after_overwrite()

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

    # A saved filename can have the wrong extension without invalidating the image.
    mislabeled = folder / "saved.jpg"
    Image.new("RGB", (64, 48)).save(mislabeled, format="PNG")
    original = mislabeled.read_bytes()
    generator = seedance.HMBSeedanceGeneration
    assert generator._read_image_for_cloud_upload(str(mislabeled)) == (original, "image/png", "saved.png")
    prepared = generator._prepare_media_reference("image", str(mislabeled))
    assert prepared.startswith("data:image/png;base64,")
    assert base64.b64decode(prepared.partition(",")[2], validate=True) == original == mislabeled.read_bytes()
    try:
        generator._prepare_media_reference("image", prepared.replace("image/png", "image/jpeg", 1))
    except ValueError as exc:
        assert "different from its declared MIME type" in str(exc)
    else:
        raise AssertionError("A mismatched data URI must still be rejected")

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

    download_url = "https://storage.example/reference.mp4?b=%2f%2B&a=2&a=1&sig=a%2Fb%3D"
    with (
        mock.patch.object(seedance.httpx, "request", side_effect=fake_request),
        mock.patch.object(driver, "create_signed_download_url", return_value=download_url) as sign,
        mock.patch.object(node, "_iter_local_video_upload_chunks", wraps=node._iter_local_video_upload_chunks) as reads,
    ):
        proven = node._upload_local_video_to_griptape_cloud(driver, upload_path, remote_path, cloud_proof_v1=True)
        reads.assert_called_once_with(upload_path)
        sign.assert_called_once_with(remote_path)
    assert proven == download_url + expected_proof(b"".join(captured["chunks"]))
    assert len(captured["chunks"]) > 1

    def partial_request(*_args, content, **_opts):
        next(iter(content))
        return SimpleNamespace(raise_for_status=lambda: None)
    interrupted_chunks = node._iter_local_video_upload_chunks(upload_path)
    with (
        mock.patch.object(seedance.httpx, "request", side_effect=partial_request),
        mock.patch.object(driver, "create_signed_download_url") as sign,
        mock.patch.object(node, "_iter_local_video_upload_chunks", return_value=interrupted_chunks),
    ):
        try:
            node._upload_local_video_to_griptape_cloud(driver, upload_path, remote_path, cloud_proof_v1=True)
        except RuntimeError as exc:
            assert "complete video reference upload body" in str(exc)
        else:
            raise AssertionError("A short signed upload received an evidence fragment")
        sign.assert_not_called()
    assert interrupted_chunks.gi_frame is None

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
    # and remote inputs are staged by the same driver. Repeating a source
    # retains each slot but creates only one upload and cleanup lease.
    image_path = folder / "cloud-reference.png"
    image_stream = BytesIO()
    with Image.new("RGB", (32, 16), (24, 105, 188)) as image:
        image.save(image_stream, format="PNG")
    image_bytes = image_stream.getvalue()
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
            return f"https://storage.example/{path.parent.name}/{path.name}?signed=opaque"

        def delete_file(self, path: Path) -> None:
            self.deletes.append(path)

    cloud_driver = LegacyCloudDriver()
    cloud_node = object.__new__(seedance.HMBSeedanceGeneration)
    cloud_node.name = "Cloud Media Transport Regression"
    cloud_node._temporary_video_uploads = []
    cloud_node._temporary_tos_video_uploads = []
    cloud_node._create_gt_cloud_storage_driver = lambda: cloud_driver
    remote_image = "https://cdn.example/already-public.png"
    downloads = []
    async def read_remote(url, *, destination, **_kwargs):
        assert url == remote_image
        downloads.append(url)
        destination.write(image_bytes)
        return b""
    cloud_node._download_external_media = read_remote
    stream = BytesIO()
    with wave.open(stream, "wb") as output:
        output.setparams((1, 2, 8000, 0, "NONE", ""))
        output.writeframes(bytes(3200))
    audio = stream.getvalue()
    audio_uri = "data:audio/wav;base64," + base64.b64encode(audio).decode("ascii")
    cloud_params = {
        "model_id": seedance.SEEDANCE_2_5_MODEL_ID,
        "first_frame": str(image_path), "last_frame": str(image_path),
        "reference_images": [image_data_uri, remote_image, {"url":remote_image}, {"path":str(image_path)}],
        "reference_audio": [audio_uri, audio_uri], "video_reference_slots": [str(upload_path), str(upload_path)],
        "auto_publish_local_videos": False, "local_video_upload_service": seedance.LOCAL_VIDEO_UPLOAD_TOS,
    }
    with (
        mock.patch.object(cloud_node, "_reference_video_upload_path", side_effect=lambda path, model: nullcontext(path)) as staged_video,
        mock.patch.object(cloud_node, "_read_image_for_cloud_upload", wraps=cloud_node._read_image_for_cloud_upload) as read_image,
        mock.patch.object(seedance, "MAX_IMAGE_BYTES", len(image_bytes) + 1),
        mock.patch.object(seedance, "TemporaryDirectory", wraps=tempfile.TemporaryDirectory) as scratch,
    ):
        ready = cloud_node._prepare_video_references_for_run(cloud_params)
    urls = [ready["first_frame"], ready["last_frame"], *ready["reference_images"],
            *ready["video_references"], *ready["reference_audio"]]
    assert len(urls) == 10
    assert all(url.startswith("https://storage.example/") for url in urls)
    assert ready["first_frame"] == ready["last_frame"] == ready["reference_images"][3]
    assert ready["reference_images"][1] == ready["reference_images"][2]
    assert ready["reference_images"][1] != ready["reference_images"][0]
    assert ready["video_references"][0] == ready["video_references"][1]
    assert ready["reference_audio"][0] == ready["reference_audio"][1]
    assert downloads == [remote_image] and staged_video.call_count == 1
    assert read_image.call_count == 3  # Path, distinct inline source, downloaded URL.
    assert sum(call.args[0] == str(image_path) for call in read_image.call_args_list) == 1
    assert len(cloud_driver.uploads) == len(cloud_node._temporary_video_uploads) == 5
    assert sum(call.kwargs.get("prefix") == "hmb-render-inputs-" for call in scratch.call_args_list) == 1
    assert cloud_params["first_frame"] == str(image_path) and cloud_params["reference_images"][2] == {"url":remote_image}
    assert [upload["file_content"] for upload in cloud_driver.uploads[:3]] == [image_bytes] * 3
    assert cloud_driver.uploads[3]["file_content"] == upload_media
    assert cloud_driver.uploads[-1]["file_content"] == audio
    assert all("#" not in url for url in urls)

    # Proofs for each slot use the bytes that this driver actually received.
    # The PNG is converted to a smaller lossless WebP before uploading.
    proof_driver = LegacyCloudDriver()
    with (
        mock.patch.object(seedance, "SEEDANCE_LOSSLESS_PNG_COPY_THRESHOLD", 1),
        mock.patch.object(cloud_node, "_reference_video_upload_path", side_effect=lambda path, model: nullcontext(path)),
    ):
        tested = cloud_node._prepare_video_references_for_run(
            dict(cloud_params, _hmb_cloud_reference_proof_v1=True), cloud_driver=proof_driver,
        )
    assert len(proof_driver.uploads) == 5
    proofs = []
    for entry in proof_driver.uploads:
        path, body = entry["path"], entry["file_content"]
        url = f"https://storage.example/{path.parent.name}/{path.name}?signed=opaque"
        proofs.append(url + expected_proof(body))
    assert tested["first_frame"] == tested["last_frame"] == proofs[0]
    assert tested["reference_images"] == [proofs[1], proofs[2], proofs[2], proofs[0]]
    assert tested["video_references"] == [proofs[3], proofs[3]]
    assert tested["reference_audio"] == [proofs[4], proofs[4]] and proof_driver.uploads[4]["file_content"] == audio
    # Only references on the final wire are in the journal. An object may occupy multiple slots.
    wire_payload = {field: tested[key] for field, key in (("image_urls", "reference_images"),
                    ("video_urls", "video_references"), ("audio_urls", "reference_audio"))}
    old_handles = cloud_node._hmb_cloud_proof_handles.copy()
    with mock.patch.dict("os.environ", {"APPDATA": str(folder)}):
        lease = cloud_node._bind_temporary_reference_lease(None, "https://broker.example", "hmb-fixture-upload", wire_payload)
        text = seedance._reference_leases._journal_path(lease).read_text(encoding="utf8")
    rows = json.loads(text)["upload_manifest"]
    assert "signed=opaque" not in text and "https://storage.example" not in text and str(folder) not in text
    assert not cloud_node._hmb_cloud_proof_handles
    expected = []
    for field, values in wire_payload.items():
        for slot, value in enumerate(values, 1):
            p = Path(old_handles[value])
            upload = next(entry for entry in proof_driver.uploads if entry["path"] == p)
            body = upload["file_content"]
            expected.append(dict(field=field, slot=slot, object_uid=p.parent.name,
                                 filename=p.name, sha256=hashlib.sha256(body).hexdigest(), bytes=len(body)))
    assert expected == rows
    # An invalid final image must fail the whole preparation before any render payload exists.
    # In particular, losing @image7 must never turn a seven-slot request into a six-slot render.
    empty_image = folder / "empty-final-reference.png"
    empty_image.write_bytes(b"")
    for invalid in (folder / "missing-final-reference.png", empty_image):
        staged = LegacyCloudDriver()
        try:
            cloud_node._prepare_video_references_for_run({
                "model_id": seedance.SEEDANCE_2_5_MODEL_ID, "_hmb_cloud_reference_proof_v1": True,
                "reference_images": [str(image_path)] * 6 + [str(invalid)],
            }, cloud_driver=staged)
        except (ValueError, RuntimeError, FileNotFoundError, OSError):
            assert not staged.uploads
        else:
            raise AssertionError("The last missing or empty reference allowed a shortened render request")
    for entry in proof_driver.uploads[:3]:
        assert entry["path"].suffix == ".webp" and entry["file_content"] != image_bytes
        with Image.open(BytesIO(entry["file_content"])) as packed, Image.open(image_path) as original:
            assert packed.format == "WEBP" and packed.tobytes() == original.tobytes()

    signed_bytes_driver = SimpleNamespace(
        create_signed_upload_url=lambda _path: {"method": "PUT", "url": "https://storage.example/upload"},
        create_signed_download_url=mock.Mock(return_value=download_url),
    )
    with mock.patch.object(seedance.httpx, "request") as put:
        for entry in (proof_driver.uploads[0], proof_driver.uploads[-1]):
            body = entry["file_content"]
            result = cloud_node._upload_cloud_reference_bytes(
                signed_bytes_driver, body, entry["path"].name, cloud_proof_v1=True,
            )
            assert put.call_args.kwargs["content"] is body
            assert put.call_args.kwargs["headers"]["Content-Length"] == str(len(body))
            assert result == download_url + expected_proof(body)
        signed_bytes_driver.create_signed_download_url.reset_mock()
        put.return_value.raise_for_status.side_effect = RuntimeError("simulated HTTP failure")
        try:
            cloud_node._upload_cloud_reference_bytes(signed_bytes_driver, audio, "clip.wav", cloud_proof_v1=True)
        except RuntimeError as exc:
            assert str(exc) == "simulated HTTP failure"
        else:
            raise AssertionError("Failed upload received a signed download URL")
        signed_bytes_driver.create_signed_download_url.assert_not_called()
    assert cloud_params["reference_images"] == [image_data_uri, remote_image, {"url":remote_image}, {"path":str(image_path)}]
    try:
        cloud_node._prepare_video_references_for_run(dict(cloud_params, video_reference_slots=[]), cloud_driver=None)
    except RuntimeError as exc:
        assert "Griptape Cloud" in str(exc)
    else:
        raise AssertionError("Missing Cloud driver allowed a render transport fallback")
    try:
        cloud_node._prepare_video_references_for_run(dict(cloud_params, first_frame="asset://opaque"))
    except ValueError as exc:
        assert "asset://" in str(exc)
    else:
        raise AssertionError("Opaque provider asset passed through without a source file")

    # Cloud readiness is one atomic credential+accessible-bucket contract.
    # A blank explicit bucket may resolve the account default. Missing auth or
    # an inaccessible configured bucket blocks preparation of render references.
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
transport_broker = "https://media-preflight.example/GripTapeServer"
token_endpoints = []


def load_fixture_token(*, server_url: str) -> str:
    assert server_url == transport_broker, (
        "Media submission must request credentials for its frozen Broker gateway."
    )
    token_endpoints.append(server_url)
    return "regression-token"


seedance._broker_transport.MAX_REQUEST_BYTES = len(expected_transport_body)
seedance._broker_transport._broker_load_token = load_fixture_token
try:
    bridge = seedance._HMBAIBrokerBridge(opener=capturing_opener, server_url=transport_broker)
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
    assert sent_request.full_url == transport_broker + "/api/v1/generate/video"
    assert sent_request.get_header("Authorization") == "Bearer regression-token"
    assert sent_request.data == expected_transport_body
    assert sent_timeout == 3.0
    assert token_endpoints == [transport_broker]

    seedance._broker_transport.MAX_REQUEST_BYTES = len(expected_transport_body) - 1
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
    assert token_endpoints and set(token_endpoints) == {transport_broker}, (
        "Every credential lookup, including rejected media, must keep its explicit Broker gateway."
    )
finally:
    seedance._broker_transport.MAX_REQUEST_BYTES = original_request_limit
    seedance._broker_transport._broker_load_token = original_load_token

print("HMB Seedance media preflight/streaming regression: PASS")
