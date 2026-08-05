from __future__ import annotations

import copy
import ast
import inspect
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


assert "PIL.Image" not in sys.modules
import _hmb_screen_space as screen  # noqa: E402


assert "PIL.Image" not in sys.modules, "The screen-space module must import Pillow lazily."
PIL_REPORT = screen.preflight_pillow()
assert PIL_REPORT["available"] is True
assert PIL_REPORT["lazy"] is True
assert screen.PROFILE == "hmb_screen_space_pattern_post_v2"
assert screen.PATTERN_LINEAR_SCALE_DIVISOR == 3
assert screen.BASE_CELL_DIVISOR == 8
assert screen.SCALED_CELL_DIVISOR == 24
assert screen.POSITION_PATTERN_REPEATS == 3
assert screen.pattern_cell_size((2048, 1152)) == 48
assert screen.pattern_cell_size((1280, 720)) == 30
assert screen.pattern_cell_size((2048, 1152)) * 3 == 1152 // 8

from PIL import Image, ImageDraw  # noqa: E402


PATTERN_IDS = {
    "direction_checker": (250, 1, 253),
    "sky_grid": (1, 252, 251),
    "floor_grid": (253, 252, 1),
    "position_pattern": (127, 3, 251),
}
DISPLAY_NAMES = {
    "direction_checker": "Direction Checker",
    "sky_grid": "Sky Grid",
    "floor_grid": "Floor Grid",
    "position_pattern": "Position Pattern",
}


def _catalog() -> dict:
    return {
        "schema": "hmb-marker-catalog",
        "version": 4,
        "character": [
            {"name": "Red", "kind": "solid", "rgb": [1.0, 0.0, 0.0]},
        ],
        "background": [
            {"name": "Sky Blue", "kind": "solid", "rgb": [0.36, 0.72, 1.0]},
            *[
                {
                    "name": DISPLAY_NAMES[pattern],
                    "kind": "pattern",
                    "pattern": pattern,
                    "screen_space_id_rgb": list(PATTERN_IDS[pattern]),
                }
                for pattern in screen.PATTERN_NAMES
            ],
        ],
    }


def _bindings(*patterns: str) -> list[dict]:
    return [
        {
            "group_name": f"|set|{pattern}",
            "color": DISPLAY_NAMES[pattern],
            "enabled": True,
        }
        for pattern in patterns
    ]


def _assert_raises(message_fragment: str, callback) -> None:
    try:
        callback()
    except screen.ScreenSpacePatternError as exc:
        assert message_fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(
            f"Expected ScreenSpacePatternError containing {message_fragment!r}."
        )


def _save_rgb(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", size, color)
    try:
        image.save(path, format="PNG")
    finally:
        image.close()


CATALOG = _catalog()
assert screen.validate_pattern_catalog(CATALOG) == PATTERN_IDS
assert screen.active_patterns_from_bindings(
    [
        *_bindings("floor_grid", "direction_checker"),
        {"color": "Sky Grid", "enabled": False},
        {"color": "Red", "enabled": True},
    ],
    CATALOG,
) == ("direction_checker", "floor_grid")

missing_id_catalog = copy.deepcopy(CATALOG)
del missing_id_catalog["background"][1]["screen_space_id_rgb"]
_assert_raises(
    "three integer channels",
    lambda: screen.validate_pattern_catalog(missing_id_catalog),
)

duplicate_id_catalog = copy.deepcopy(CATALOG)
duplicate_id_catalog["background"][2]["screen_space_id_rgb"] = list(
    PATTERN_IDS["direction_checker"]
)
_assert_raises(
    "shared",
    lambda: screen.validate_pattern_catalog(duplicate_id_catalog),
)

fractional_id_catalog = copy.deepcopy(CATALOG)
fractional_id_catalog["background"][1]["screen_space_id_rgb"] = [250.0, 1, 253]
_assert_raises(
    "integers",
    lambda: screen.validate_pattern_catalog(fractional_id_catalog),
)


with tempfile.TemporaryDirectory(prefix="HMB_Screen_Space_") as temporary_folder:
    root = Path(temporary_folder)

    # Two separated regions carrying one ID inherit phase from the same frame origin.
    separated_path = root / "separated.png"
    separated = Image.new("RGB", (64, 32), (12, 34, 56))
    try:
        for y in range(1, 4):
            for x in range(1, 4):
                separated.putpixel((x, y), PATTERN_IDS["direction_checker"])
            for x in range(5, 8):
                separated.putpixel((x, y), PATTERN_IDS["direction_checker"])
        separated.save(separated_path, format="PNG")
    finally:
        separated.close()

    separated_report = screen.postprocess_marker_frames(
        [separated_path],
        catalog=CATALOG,
        bindings=_bindings("direction_checker"),
        expected_size=(64, 32),
    )
    assert separated_report["profile"] == "hmb_screen_space_pattern_post_v2"
    assert separated_report["pattern_linear_scale_divisor"] == 3
    assert separated_report["pattern_cell_pixels"] == 4
    assert separated_report["position_pattern_repeats"] == 3
    assert separated_report["uv_dependent"] is False
    assert separated_report["phase"] == "frame_top_left"
    assert separated_report["origin"] == {"x": 0, "y": 0, "edge": "top_left"}
    assert separated_report["frames_processed"] == 1
    assert separated_report["frames_rewritten"] == 1
    assert separated_report["replaced"]["total_pixels"] == 18
    assert separated_report["replaced"]["by_pattern"] == {
        "direction_checker": 18
    }
    with Image.open(separated_path) as result:
        result.load()
        assert result.getpixel((1, 1)) == (0, 0, 0)
        assert result.getpixel((5, 1)) == (255, 255, 255)
        assert result.getpixel((40, 10)) == (12, 34, 56)

    # Every pattern is generated against one non-square full-frame canvas.
    size = (80, 48)
    pattern_paths: list[Path] = []
    for pattern in screen.PATTERN_NAMES:
        path = root / f"{pattern}.png"
        _save_rgb(path, size, PATTERN_IDS[pattern])
        pattern_paths.append(path)

    all_report = screen.postprocess_marker_frames(
        pattern_paths,
        catalog=CATALOG,
        bindings=_bindings(*screen.PATTERN_NAMES),
        expected_size=size,
    )
    pixels_per_frame = size[0] * size[1]
    assert all_report["expected_size"] == {"width": 80, "height": 48}
    assert all_report["frames_seen"] == 4
    assert all_report["frames_processed"] == 4
    assert all_report["frames_rewritten"] == 4
    assert all_report["profile"] == "hmb_screen_space_pattern_post_v2"
    assert all_report["pattern_linear_scale_divisor"] == 3
    assert all_report["pattern_cell_pixels"] == 4
    assert all_report["position_pattern_repeats"] == 3
    assert all_report["replaced"]["total_pixels"] == pixels_per_frame * 4
    assert all_report["replaced"]["by_pattern"] == {
        pattern: pixels_per_frame for pattern in screen.PATTERN_NAMES
    }

    with Image.open(root / "direction_checker.png") as result:
        result.load()
        assert result.size == size
        assert result.getpixel((1, 1)) == (0, 0, 0)
        assert result.getpixel((5, 1)) == (255, 255, 255)

    with Image.open(root / "sky_grid.png") as result:
        result.load()
        assert result.getpixel((1, 1)) == (255, 255, 255)
        assert result.getpixel((10, 10)) == (67, 155, 231)
        assert result.getpixel((4, 3)) == (191, 242, 255)
        assert result.getpixel((16, 10)) == (255, 255, 255)

    with Image.open(root / "floor_grid.png") as result:
        result.load()
        assert result.getpixel((1, 1)) == (255, 231, 151)
        assert result.getpixel((10, 10)) == (132, 107, 66)
        assert result.getpixel((6, 2)) == (105, 83, 51)

    with Image.open(root / "position_pattern.png") as result:
        result.load()
        assert result.getpixel((1, 1)) == (239, 65, 65)
        assert result.getpixel((78, 1)) == (62, 205, 119)
        assert result.getpixel((1, 46)) == (57, 104, 232)
        assert result.getpixel((78, 46)) == (246, 210, 49)
        assert result.getpixel((40, 24)) == (255, 255, 255)
        # The original four-quadrant motif repeats three times on each axis,
        # making every colored region one third of its former linear size.
        assert result.getpixel((20, 2)) == (62, 205, 119)
        assert result.getpixel((2, 13)) == (57, 104, 232)
        assert result.getpixel((20, 13)) == (246, 210, 49)
        assert result.getpixel((28, 1)) == (239, 65, 65)
        assert result.getpixel((2, 18)) == (239, 65, 65)

    # Production-resolution pixel locks prevent the minimum-cell fallback used
    # by tiny fixtures from hiding a scale regression. At 2048x1152, the old
    # /8 pattern cell was 144 px and the approved /24 cell is exactly 48 px.
    production_size = (2048, 1152)
    direction = screen._pattern_canvas(
        "direction_checker", production_size, Image, ImageDraw
    )
    try:
        assert direction.getpixel((47, 10)) == (0, 0, 0)
        assert direction.getpixel((48, 10)) == (255, 255, 255)
        assert direction.getpixel((95, 10)) == (255, 255, 255)
        assert direction.getpixel((96, 10)) == (0, 0, 0)
    finally:
        direction.close()

    sky = screen._pattern_canvas(
        "sky_grid", production_size, Image, ImageDraw
    )
    try:
        assert sky.getpixel((3, 10)) == (255, 255, 255)
        assert sky.getpixel((4, 10)) == (67, 155, 231)
        assert sky.getpixel((48, 10)) == (191, 242, 255)
        assert sky.getpixel((50, 10)) == (67, 155, 231)
        assert sky.getpixel((195, 10)) == (255, 255, 255)
        assert sky.getpixel((196, 10)) == (67, 155, 231)
    finally:
        sky.close()

    floor = screen._pattern_canvas(
        "floor_grid", production_size, Image, ImageDraw
    )
    try:
        assert floor.getpixel((2, 10)) == (255, 231, 151)
        assert floor.getpixel((3, 10)) == (132, 107, 66)
        assert floor.getpixel((47, 10)) == (132, 107, 66)
        assert floor.getpixel((50, 10)) == (255, 231, 151)
        assert floor.getpixel((51, 10)) == (105, 83, 51)
    finally:
        floor.close()

    position = screen._pattern_canvas(
        "position_pattern", production_size, Image, ImageDraw
    )
    try:
        assert position.getpixel((100, 100)) == (239, 65, 65)
        assert position.getpixel((400, 100)) == (62, 205, 119)
        assert position.getpixel((100, 300)) == (57, 104, 232)
        assert position.getpixel((400, 300)) == (246, 210, 49)
        assert position.getpixel((700, 100)) == (239, 65, 65)
        assert position.getpixel((100, 500)) == (239, 65, 65)
        assert position.getpixel((341, 100)) == (255, 255, 255)
        assert position.getpixel((100, 192)) == (255, 255, 255)
    finally:
        position.close()

    # Position Pattern replacement is exact and restricted to its categorical
    # ID. Neighboring beauty pixels must remain byte-for-byte unchanged.
    position_partial_path = root / "position_pattern_partial.png"
    position_partial_source = Image.new("RGB", (20, 12), (12, 34, 56))
    try:
        position_partial_source.putpixel((0, 0), PATTERN_IDS["position_pattern"])
        position_partial_source.save(position_partial_path, format="PNG")
    finally:
        position_partial_source.close()
    position_partial_report = screen.postprocess_marker_frames(
        [position_partial_path],
        catalog=CATALOG,
        bindings=_bindings("position_pattern"),
        expected_size=(20, 12),
    )
    assert position_partial_report["replaced"]["total_pixels"] == 1
    with Image.open(position_partial_path) as result:
        result.load()
        assert result.getpixel((0, 0)) == (239, 65, 65)
        assert result.getpixel((1, 0)) == (12, 34, 56)

    assert not list(root.glob(".*.hmb-screen-space.tmp.png"))

    # No active pattern is a true no-op: no file access and no Pillow processing.
    no_op_report = screen.postprocess_marker_frames(
        [root / "not-created.png"],
        catalog=CATALOG,
        bindings=[{"color": "Red", "enabled": True}],
        expected_size=(1920, 1080),
    )
    assert no_op_report["no_op"] is True
    assert no_op_report["frames_seen"] == 1
    assert no_op_report["frames_processed"] == 0
    assert no_op_report["replaced"]["total_pixels"] == 0

    missing_path = root / "missing.png"
    _assert_raises(
        "does not exist",
        lambda: screen.postprocess_marker_frames(
            [missing_path],
            catalog=CATALOG,
            bindings=_bindings("direction_checker"),
            expected_size=(16, 16),
        ),
    )

    corrupt_path = root / "corrupt.png"
    corrupt_path.write_bytes(b"not a png")
    _assert_raises(
        "corrupt or unreadable",
        lambda: screen.postprocess_marker_frames(
            [corrupt_path],
            catalog=CATALOG,
            bindings=_bindings("direction_checker"),
            expected_size=(16, 16),
        ),
    )

    wrong_size_path = root / "wrong-size.png"
    _save_rgb(wrong_size_path, (17, 16), PATTERN_IDS["direction_checker"])
    _assert_raises(
        "size mismatch",
        lambda: screen.postprocess_marker_frames(
            [wrong_size_path],
            catalog=CATALOG,
            bindings=_bindings("direction_checker"),
            expected_size=(16, 16),
        ),
    )


# Public processing inputs contain only frames, catalog, bindings, and frame size.
parameters = inspect.signature(screen.postprocess_marker_frames).parameters
assert tuple(parameters) == ("frame_paths", "catalog", "bindings", "expected_size")
for parameter in parameters:
    lowered = parameter.lower()
    assert "bbox" not in lowered
    assert "uv" not in lowered
    assert "object" not in lowered

source = Path(screen.__file__).read_text(encoding="utf-8").lower()
source_without_required_report_key = source.replace('"uv_dependent"', "")
assert "getbbox(" not in source_without_required_report_key
assert "bounding_box" not in source_without_required_report_key
assert "uv_coordinate" not in source_without_required_report_key
assert "object_coordinate" not in source_without_required_report_key


# Picker integration must preflight Pillow before Maya, then replace the raw
# categorical PNGs before a snapshot copy or FFmpeg command can consume them.
picker_path = ROOT / "HMBVideoPickerLibrary.py"
picker_source = picker_path.read_text(encoding="utf-8")
picker_tree = ast.parse(picker_source, filename=str(picker_path))


def _function_source(name: str) -> str:
    matches = [
        node
        for node in ast.walk(picker_tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1
    node = matches[0]
    return "\n".join(
        picker_source.splitlines()[node.lineno - 1 : node.end_lineno]
    )


snapshot_source = _function_source("_snapshot_mode")
playblast_source = _function_source("_maya_mode")
encode_source = _function_source("_encode_playblast_sequence")
for function_source in (snapshot_source, playblast_source):
    assert '"force_high_quality_viewport": True' in function_source
    assert '"require_full_smooth_geometry": True' in function_source
    assert '"screen_space_patterns": True' in function_source
    assert "_screen_space_preflight(" in function_source
assert snapshot_source.index("_postprocess_screen_space_frames(") < snapshot_source.index(
    "shutil.copy2(rendered_path, staged_cache_path)"
)
assert playblast_source.index("_postprocess_screen_space_frames(") < playblast_source.index(
    "self._encode_playblast_sequence("
)
assert "_build_ffmpeg_encode_command(" in encode_source


print(
    "HMB screen-space pattern regression passed: lazy Pillow, strict catalog IDs, "
    "global top-left phase, four visible patterns at one-third linear scale, "
    "non-square streaming, exact beauty pixel preservation, atomic PNG publish, "
    "and fail-closed frame validation."
)
