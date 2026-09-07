from __future__ import annotations
import copy
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _hmb_video_tools as target
video_state = target.default_picker_tools_state()

assert target.calculate_crop_rectangle(1920, 1080, {"crop_size": "720p", "crop_position": "center"}) == (
    1280,
    720,
    320,
    180,
)
assert target.calculate_crop_rectangle(
    1920,
    1080,
    {
        "crop_size": "Custom",
        "crop_position": "Custom",
        "custom_width": 641,
        "custom_height": 481,
        "custom_left": 2000,
        "custom_top": 2000,
    },
) == (640, 480, 1280, 600)

crop_command = target.build_crop_ffmpeg_command(
    "ffmpeg",
    "input.mp4",
    "output.mp4",
    (1280, 720, 320, 180),
    has_audio=True,
)
assert crop_command[0] == "ffmpeg"
assert "crop=1280:720:320:180" in crop_command
assert crop_command[-1] == "output.mp4"
assert "-c:a" in crop_command and "copy" in crop_command

concat_command = target.build_concat_ffmpeg_command(
    "ffmpeg",
    "inputs.txt",
    "output.mp4",
    video_state["concatenate"],
)
assert concat_command[0] == "ffmpeg"
assert concat_command[-1] == "output.mp4"
assert concat_command[concat_command.index("-f") + 1] == "concat"
assert concat_command[concat_command.index("-safe") + 1] == "0"

filter_concat_command = target.build_filter_concat_ffmpeg_command(
    "ffmpeg",
    ["first.mov", "second.mp4"],
    "output.mp4",
    video_state["concatenate"],
    [
        {"width": 320, "height": 240, "frame_rate": 24.0, "duration": 0.4, "has_audio": True},
        {"width": 640, "height": 360, "frame_rate": 30.0, "duration": 0.4, "has_audio": False},
    ],
)
assert filter_concat_command.index("first.mov") < filter_concat_command.index("second.mp4")
filter_graph = filter_concat_command[filter_concat_command.index("-filter_complex") + 1]
assert "fps=24" in filter_graph
assert "scale=320:240" in filter_graph
assert "settb=AVTB" in filter_graph
assert "aresample=48000" in filter_graph
assert "anullsrc=r=48000:cl=stereo" in filter_graph
assert "[v0][a0][v1][a1]concat=n=2:v=1:a=1[vout][aout]" in filter_graph

webm_settings = copy.deepcopy(video_state["concatenate"])
webm_settings.update({"output_format": "webm", "video_codec": "libvpx-vp9", "audio_codec": "libopus"})
webm_command = target.build_filter_concat_ffmpeg_command(
    "ffmpeg",
    ["first.mov", "second.mp4"],
    "output.webm",
    webm_settings,
    [
        {"width": 320, "height": 240, "frame_rate": 24.0, "duration": 0.4, "has_audio": True},
        {"width": 320, "height": 240, "frame_rate": 24.0, "duration": 0.4, "has_audio": True},
    ],
)
assert webm_command[webm_command.index("-c:v") + 1] == "libvpx-vp9"
assert webm_command[webm_command.index("-c:a") + 1] == "libopus"
assert "-deadline" in webm_command and "-cpu-used" in webm_command and "-b:v" in webm_command
assert "-preset" not in webm_command
mp3_settings = copy.deepcopy(video_state["concatenate"])
mp3_settings["audio_codec"] = "mp3"
mp3_command = target.build_filter_concat_ffmpeg_command(
    "ffmpeg",
    ["first.mov", "second.mp4"],
    "output.mkv",
    mp3_settings,
    [
        {"width": 320, "height": 240, "frame_rate": 24.0, "duration": 0.4, "has_audio": True},
        {"width": 320, "height": 240, "frame_rate": 24.0, "duration": 0.4, "has_audio": True},
    ],
)
assert mp3_command[mp3_command.index("-c:a") + 1] == "libmp3lame"

# Exercise the bundled FFmpeg path with heterogeneous videos. Temporary files
# are isolated from the project and disappear even when an assertion fails.
with tempfile.TemporaryDirectory(prefix="hmb_finish_look_test_") as temp_name:
    temp_dir = Path(temp_name)
    ffmpeg = target._find_ffmpeg()
    source_paths = []
    source_specs = (
        ("red", "libx264", 24, 48_000, 320, 240),
        ("blue", "mpeg4", 30, 44_100, 640, 360),
    )
    for index, (color, codec, frame_rate, sample_rate, width, height) in enumerate(source_specs, start=1):
        suffix = "'s" if index == 2 else ""
        source_path = temp_dir / f"source_{index}{suffix}.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s={width}x{height}:r={frame_rate}:d=0.4",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={index * 440}:sample_rate={sample_rate}:duration=0.4",
                "-shortest",
                "-c:v",
                codec,
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-y",
                str(source_path),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        source_paths.append(source_path)

    media_service = target.VideoMediaService()
    concat_settings = copy.deepcopy(video_state["concatenate"])
    concat_settings.update(
        {
            "inputs": [str(path) for path in source_paths],
            "output_path": str(temp_dir / "joined.mp4"),
        }
    )
    concat_result = media_service.concatenate(concat_settings)
    assert Path(concat_result["path"]).is_file()
    assert concat_result["input_count"] == 2
    assert concat_result["width"] == 320 and concat_result["height"] == 240
    assert concat_result["has_audio"] is True
    assert 0.7 <= concat_result["duration"] <= 0.95

    def sampled_rgb(path, timestamp):
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(timestamp),
                "-i",
                str(path),
                "-vf",
                "scale=1:1",
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        assert len(completed.stdout) >= 3
        return tuple(completed.stdout[:3])

    first_rgb = sampled_rgb(concat_result["path"], 0.1)
    second_rgb = sampled_rgb(concat_result["path"], 0.6)
    assert first_rgb[0] > first_rgb[2] + 100, first_rgb
    assert second_rgb[2] > second_rgb[0] + 100, second_rgb

    # A copy request stays on the concat-demuxer path and is accepted only for
    # stream-identical inputs. Apostrophes in the concat list remain safe.
    copy_settings = copy.deepcopy(video_state["concatenate"])
    copy_settings.update(
        {
            "inputs": [str(source_paths[0]), str(source_paths[0])],
            "output_path": str(temp_dir / "joined-copy.mp4"),
            "video_codec": "copy",
            "audio_codec": "copy",
        }
    )
    copy_result = media_service.concatenate(copy_settings)
    assert Path(copy_result["path"]).is_file()
    assert copy_result["duration"] >= 0.7
    incompatible_copy = copy.deepcopy(copy_settings)
    incompatible_copy.update(
        {
            "inputs": [str(path) for path in source_paths],
            "output_path": str(temp_dir / "incompatible-copy.mp4"),
        }
    )
    try:
        media_service.concatenate(incompatible_copy)
    except target.VideoToolError as exc:
        assert "Stream copy requires matching" in str(exc)
    else:
        raise AssertionError("Heterogeneous inputs bypassed stream-copy compatibility validation")

    # Silent inputs remain silent, while a mixed audio/silent sequence receives
    # bounded synthesized silence and preserves the complete duration.
    silent_paths = []
    for index, (color, frame_rate, width, height) in enumerate(
        (("yellow", 25, 240, 160), ("green", 30, 320, 240)),
        start=1,
    ):
        silent_path = temp_dir / f"silent_{index}.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s={width}x{height}:r={frame_rate}:d=0.35",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-y",
                str(silent_path),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        silent_paths.append(silent_path)
    silent_settings = copy.deepcopy(video_state["concatenate"])
    silent_settings.update(
        {
            "inputs": [str(path) for path in silent_paths],
            "output_path": str(temp_dir / "joined-silent.mp4"),
        }
    )
    silent_result = media_service.concatenate(silent_settings)
    assert silent_result["has_audio"] is False
    assert silent_result["duration"] >= 0.6
    mixed_settings = copy.deepcopy(video_state["concatenate"])
    mixed_settings.update(
        {
            "inputs": [str(source_paths[0]), str(silent_paths[0])],
            "output_path": str(temp_dir / "joined-mixed-audio.mp4"),
        }
    )
    mixed_result = media_service.concatenate(mixed_settings)
    assert mixed_result["has_audio"] is True
    assert mixed_result["duration"] >= 0.65

    webm_settings = copy.deepcopy(video_state["concatenate"])
    webm_settings.update(
        {
            "inputs": [str(path) for path in source_paths],
            "output_path": str(temp_dir / "joined.webm"),
            "output_format": "webm",
            "video_codec": "libvpx-vp9",
            "audio_codec": "libopus",
        }
    )
    webm_result = media_service.concatenate(webm_settings)
    assert Path(webm_result["path"]).is_file()
    assert webm_result["has_audio"] is True
    assert webm_result["duration"] >= 0.7
    incompatible_webm = copy.deepcopy(webm_settings)
    incompatible_webm.update(
        {
            "output_path": str(temp_dir / "bad.webm"),
            "video_codec": "libx264",
            "audio_codec": "aac",
        }
    )
    try:
        media_service.concatenate(incompatible_webm)
    except target.VideoToolError as exc:
        assert "WebM output requires" in str(exc)
    else:
        raise AssertionError("An invalid WebM codec pair reached FFmpeg")

    # The packaged imageio-ffmpeg runtime does not include ffprobe. Force the
    # stderr parser to prove normal transcodes still validate 48 kHz stereo,
    # while stream copy remains fail-closed without full stream metadata.
    original_find_ffprobe = target._find_ffprobe
    target._find_ffprobe = lambda _ffmpeg=None: ""
    try:
        fallback_probe = target.probe_video(concat_result["path"])
        assert fallback_probe["probe_backend"] == "ffmpeg"
        assert fallback_probe["audio_sample_rate"] == 48_000
        assert fallback_probe["audio_channels"] == 2
        assert fallback_probe["audio_channel_layout"] == "stereo"
        fallback_settings = copy.deepcopy(concat_settings)
        fallback_settings["output_path"] = str(temp_dir / "joined-fallback-probe.mp4")
        fallback_result = media_service.concatenate(fallback_settings)
        assert Path(fallback_result["path"]).is_file()
        fallback_copy_settings = copy.deepcopy(copy_settings)
        fallback_copy_settings["output_path"] = str(temp_dir / "copy-without-ffprobe.mp4")
        try:
            media_service.concatenate(fallback_copy_settings)
        except target.VideoToolError as exc:
            assert "complete FFprobe stream metadata" in str(exc)
        else:
            raise AssertionError("Stream copy did not fail closed when FFprobe metadata was unavailable")
    finally:
        target._find_ffprobe = original_find_ffprobe

    class TruncatingVideoService(target.VideoMediaService):
        def _run(self, command, cancel_event=None, *, timeout=target.VIDEO_PROCESS_TIMEOUT_SECONDS):
            shutil.copyfile(source_paths[0], command[-1])
            return "synthetic truncated output"

    truncated_settings = copy.deepcopy(concat_settings)
    truncated_settings["output_path"] = str(temp_dir / "truncated.mp4")
    try:
        TruncatingVideoService().concatenate(truncated_settings)
    except target.VideoToolError as exc:
        assert "incomplete concatenation" in str(exc)
    else:
        raise AssertionError("A truncated FFmpeg output was reported as a successful concatenation")

    crop_settings = copy.deepcopy(video_state["crop"])
    crop_settings.update(
        {
            "input": concat_result["path"],
            "output_path": str(temp_dir / "cropped.mp4"),
            "crop_size": "Custom",
            "crop_position": "center",
            "custom_width": 160,
            "custom_height": 120,
        }
    )
    crop_result = media_service.crop(crop_settings)
    assert Path(crop_result["path"]).is_file()
    assert crop_result["width"] == 160 and crop_result["height"] == 120
    assert crop_result["left"] == 80 and crop_result["top"] == 60
    assert crop_result["has_audio"] is True
    assert crop_result["duration"] >= 0.7

print("Shared Video Tools engine: heterogeneous concat, codecs, audio normalization, probe fallback, crop passed.")
