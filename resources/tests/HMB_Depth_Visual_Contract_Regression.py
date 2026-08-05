from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys
import tempfile
from typing import Callable

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load regression target: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


picker = load("HMBVideoPickerLibrary")
prompt = load("HMBPromptLibrary")


EXPECTED_PROFILE = "hmb_camera_space_depth_v7"
LEGACY_PROFILES = (
    "hmb_camera_space_depth_v1",
    "hmb_camera_space_depth_v2",
    "hmb_camera_space_depth_v3",
    "hmb_camera_space_depth_v4",
    "hmb_camera_space_depth_v5",
    "hmb_camera_space_depth_v6",
)
FRAME_COUNT = 7
WIDTH = 192
HEIGHT = 128
FPS = 24.0
START_FRAME = 101.0
END_FRAME = START_FRAME + FRAME_COUNT - 1
CAMERA = "|shotCam"


assert picker.DEPTH_PLAYBLAST_PROFILE == EXPECTED_PROFILE
assert prompt.PICKER_DEPTH_PROFILE == EXPECTED_PROFILE
assert set(LEGACY_PROFILES) == set(picker.LEGACY_DEPTH_PLAYBLAST_PROFILES)


def frame_map() -> list[dict]:
    return [
        {
            "sequence_index": index,
            "maya_frame": START_FRAME + index,
        }
        for index in range(FRAME_COUNT)
    ]


def range_report() -> dict:
    return {
        "profile": picker.DEPTH_PLAYBLAST_PROFILE,
        "space": "camera",
        "source": "object_bbox_camera_depth",
        "assignment_mode": "color_picker_style_shared_gray_material_buckets",
        "depth_update_scope": "per_shape_path_per_output_frame",
        "representative_depth": (
            "median_positive_camera_depth_of_world_bbox_corners"
        ),
        "normalization_policy": "screen_valid_foreground_percentile_bounds",
        "near": 2.0,
        "far": 250.0,
        "camera_near_clip": 0.1,
        "camera_far_clip": 1000.0,
        "camera_near_clip_min": 0.1,
        "camera_near_clip_max": 0.1,
        "camera_far_clip_min": 1000.0,
        "camera_far_clip_max": 1000.0,
        "camera_clip_animated": False,
        "camera_origin_distance": 0.0,
        "camera_clip_is_hard_safety_boundary": True,
        "range_evaluation_scope": "complete_requested_sequence",
        "range_evaluated_frame_count": FRAME_COUNT,
        "shot_range_sample": {
            "evaluation_scope": "complete_requested_sequence",
            "evaluated_frame_count": FRAME_COUNT,
            "evaluated_frames": [START_FRAME + index for index in range(FRAME_COUNT)],
            "representative_sample_count": 2 * FRAME_COUNT,
            "foreground_representative_sample_count": 2 * FRAME_COUNT,
            "context_representative_sample_count": 0,
            "screen_rejected_representative_sample_count": 0,
            "role_excluded_representative_sample_count": 0,
            "normalization_candidate_shape_path_count": 2,
            "screen_sample_tested_bbox_count": 2 * FRAME_COUNT,
            "screen_sample_visible_bbox_count": 2 * FRAME_COUNT,
            "screen_sample_rejected_bbox_count": 0,
            "bbox_fallback_candidate_count": 0,
            "foreground_near_percentile": 0.01,
            "foreground_far_percentile": 0.99,
            "generic_far_percentile": 0.95,
            "generic_percentile_min_shapes": 20,
            "screen_sample_policy": "deterministic_api_mesh_vertices_and_polygon_centers;bbox_fallback_when_sampling_unavailable",
            "rejection_accounting_policy": "disjoint_normalization_outcomes",
            "screen_vertex_sample_limit": 128,
            "screen_polygon_center_sample_limit": 64,
            "range_candidate_scope": "screen_valid_foreground_actor_shapes",
            "range_basis": "complete_sequence_screen_valid_foreground_representative_percentiles",
            "near_anchor": "effective_screen_valid_foreground_near",
            "fallback_percentile": None,
            "fallback_reason": "",
            "range_extrema_sources": {
                "near": {
                    "frame": START_FRAME,
                    "shape": "|Actor|NearShape",
                    "root": "|Actor",
                    "marker": "Red",
                    "role": "foreground",
                    "representative_depth": 2.0,
                    "screen_sample_policy": "api_mesh_vertex_polygon_center_screen_visible",
                    "used_bbox_fallback": False,
                    "screen_inside_sample_count": 4,
                },
                "far": {
                    "frame": END_FRAME,
                    "shape": "|Actor|FarShape",
                    "root": "|Actor",
                    "marker": "Red",
                    "role": "foreground",
                    "representative_depth": 250.0,
                    "screen_sample_policy": "api_mesh_vertex_polygon_center_screen_visible",
                    "used_bbox_fallback": False,
                    "screen_inside_sample_count": 4,
                },
            },
            "binding_range_reports": [{
                "root": "|Actor",
                "marker": "Red",
                "role": "foreground",
                "shape_path_count": 2,
                "representative_sample_count": 2 * FRAME_COUNT,
                "representative_near": 2.0,
                "representative_far": 250.0,
                "normalization_candidate_sample_count": 2 * FRAME_COUNT,
                "normalization_candidate_near": 2.0,
                "normalization_candidate_far": 250.0,
                "screen_tested_shape_path_count": 2,
                "screen_visible_shape_path_count": 2,
                "screen_rejected_shape_path_count": 0,
                "bbox_fallback_shape_path_count": 0,
                "role_excluded_shape_path_count": 0,
                "screen_sample_count": 2 * FRAME_COUNT,
                "screen_visible_sample_count": 2 * FRAME_COUNT,
                "screen_sample_policy_counts": {
                    "api_mesh_vertex_polygon_center_screen_visible": 2 * FRAME_COUNT,
                },
                "selected_for_normalization": True,
            }],
        },
        "near_color": [0.9, 0.9, 0.9],
        "far_color": [0.0, 0.0, 0.0],
        "output_value_range": [0.0, 0.9],
        "camera_near_safety_margin": 0.1,
        "reserved_output_value_range": [0.9, 1.0],
        "direction": "near_white_far_black",
        "background": "pure_black",
        "temporal_normalization": "fixed_for_complete_sequence",
        "encoding_curve": "normalized_power",
        "contrast_exponent": 1.0,
        "renderable_shape_count": 2,
        "mesh_shape_count": 2,
        "nurbs_surface_shape_count": 0,
        "proxy_preview_recovery": {
            "candidate_shape_count": 0,
            "candidate_path_count": 0,
            "recovered_shape_count": 0,
            "recovered_path_count": 0,
            "recovered_paths": [],
            "source_paths": [],
        },
        "assignment_verification": {
            "shape_path_count": 2,
            "mesh_path_count": 2,
            "nurbs_surface_path_count": 0,
            "verified_shape_path_count": 2,
            "verified_mesh_face_count": 24,
            "rendered_frame_count": FRAME_COUNT,
            "expected_frame_assignment_count": 2 * FRAME_COUNT,
            "verified_frame_assignment_count": 2 * FRAME_COUNT,
        },
        "shader_model": "surfaceShader",
        "grayscale_bucket_count": 256,
        "standard_nodes": ["surfaceShader"],
        "cutout_transparency": {
            "policy": "preserve_authored_material_out_transparency_v1",
            "captured_shape_path_count": 2,
            "alpha_driven_shape_path_count": 1,
            "source_plug_count": 1,
            "verified_shape_path_count": 1,
            "ambiguous_shape_path_count": 0,
            "unsupported_shape_path_count": 0,
        },
        "render_options": {
            "output_transform_disabled": True,
            "multisample_disabled": True,
            "line_aa_disabled": True,
            "ssao_disabled": True,
            "motion_blur_disabled": True,
            "depth_of_field_disabled": True,
            "fog_disabled": True,
        },
    }


def common_sidecar() -> dict:
    return {
        "frame_count": FRAME_COUNT,
        "fps": FPS,
        "start_frame": START_FRAME,
        "end_frame": END_FRAME,
        "resolution": {"width": WIDTH, "height": HEIGHT},
        "camera": CAMERA,
        "frame_map": frame_map(),
    }


def smooth_depth_value(x: int, y: int, frame_index: int) -> int:
    """Continuous sloped/curved surface with a small coherent time shift."""

    # A narrow unoccupied strip models the shader's required pure-black
    # background without turning the rendered geometry into a binary mask.
    if y < HEIGHT // 12:
        return 0
    horizontal = x / (WIDTH - 1)
    vertical = (2.0 * y / (HEIGHT - 1)) - 1.0
    curved = 1.0 - (vertical * vertical)
    wave = 0.025 * math.sin((horizontal * math.tau) + frame_index * 0.12)
    normalized = max(0.0, min(1.0, (0.58 * horizontal) + (0.42 * curved) + wave))
    return int(round(10.0 + (232.0 * normalized)))


def binary_depth_value(x: int, _y: int, _frame_index: int) -> int:
    return 255 if x < WIDTH // 2 else 0


def posterized_depth_value(x: int, _y: int, _frame_index: int) -> int:
    return (0, 85, 170, 250)[min(3, x * 4 // WIDTH)]


def noise_depth_value(x: int, y: int, frame_index: int) -> int:
    # Deterministic spatial hash: broad histogram, but no depth-like continuity.
    value = (x * 73) ^ (y * 151) ^ (frame_index * 199) ^ (x * y * 17)
    return value & 255


def flat_depth_value(x: int, y: int, _frame_index: int) -> int:
    if WIDTH // 4 <= x < (3 * WIDTH) // 4 and HEIGHT // 4 <= y < (3 * HEIGHT) // 4:
        return 128
    return 0


def sparse_depth_value(x: int, y: int, _frame_index: int) -> int:
    if x < 4 and y < 4:
        return 40 + (x * 10) + y
    return 0


def no_visible_depth_value(_x: int, _y: int, _frame_index: int) -> int:
    return 0


DepthGenerator = Callable[[int, int, int], int]


def write_fixture_frames(
    root: Path,
    name: str,
    depth_generator: DepthGenerator,
) -> tuple[list[Path], list[Path]]:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    color_paths: list[Path] = []
    depth_paths: list[Path] = []
    for frame_index in range(FRAME_COUNT):
        color_path = folder / f"color.{frame_index:06d}.png"
        depth_path = folder / f"depth.{frame_index:06d}.png"
        color = Image.new("RGB", (WIDTH, HEIGHT))
        color.putdata([
            (
                (x * 3 + frame_index * 5) & 255,
                (y * 5 + frame_index * 7) & 255,
                ((x + y) * 2 + frame_index * 11) & 255,
            )
            for y in range(HEIGHT)
            for x in range(WIDTH)
        ])
        depth = Image.new("L", (WIDTH, HEIGHT))
        depth.putdata([
            depth_generator(x, y, frame_index)
            for y in range(HEIGHT)
            for x in range(WIDTH)
        ])
        color.save(color_path)
        depth.save(depth_path)
        color_paths.append(color_path)
        depth_paths.append(depth_path)
    return color_paths, depth_paths


def validation_payloads() -> tuple[dict, dict, dict]:
    color_sidecar = common_sidecar()
    depth_sidecar = {
        **common_sidecar(),
        "schema": "hmb-maya-depth-playblast",
        "schema_version": 1,
        "profile": picker.DEPTH_PLAYBLAST_PROFILE,
        "depth_range_report": range_report(),
    }
    result = {
        "depth_profile": picker.DEPTH_PLAYBLAST_PROFILE,
        "depth_frame_count": FRAME_COUNT,
        "depth_frame_map": frame_map(),
        "depth_range_report": range_report(),
    }
    return result, color_sidecar, depth_sidecar


def validate(
    color_paths: list[Path],
    depth_paths: list[Path],
    *,
    mutate: Callable[[dict, dict, dict], None] | None = None,
) -> dict:
    result, color_sidecar, depth_sidecar = validation_payloads()
    if mutate is not None:
        mutate(result, color_sidecar, depth_sidecar)
    return picker._validate_depth_companion_inputs(
        result=result,
        color_sidecar=color_sidecar,
        depth_sidecar=depth_sidecar,
        color_frame_paths=color_paths,
        depth_frame_paths=depth_paths,
        expected_frame_count=FRAME_COUNT,
        expected_fps=FPS,
        expected_start_frame=START_FRAME,
        expected_end_frame=END_FRAME,
        expected_width=WIDTH,
        expected_height=HEIGHT,
    )


def assert_rejected(label: str, operation: Callable[[], object], fragment: str) -> None:
    try:
        operation()
    except RuntimeError as exc:
        message = str(exc)
        assert fragment.casefold() in message.casefold(), (
            f"{label} was rejected for the wrong reason: {message}"
        )
    else:
        raise AssertionError(f"{label} must fail closed.")


with tempfile.TemporaryDirectory(prefix="hmb-depth-visual-contract-") as temp_dir:
    fixture_root = Path(temp_dir)
    smooth_color, smooth_depth = write_fixture_frames(
        fixture_root,
        "smooth",
        smooth_depth_value,
    )

    smooth_report = validate(smooth_color, smooth_depth)
    assert smooth_report["validated"] is True
    assert smooth_report["profile"] == EXPECTED_PROFILE
    assert smooth_report["frame_map_match"] is True
    assert smooth_report["cutout_transparency"] == (
        range_report()["cutout_transparency"]
    )
    assert smooth_report["quality_passed_frames"] == FRAME_COUNT
    assert smooth_report["quality_required_frames"] == math.ceil(
        FRAME_COUNT * picker.DEPTH_QUALITY_MIN_PASS_FRACTION
    )
    assert smooth_report["quality_medians"]["meaningful_levels"] >= (
        picker.DEPTH_QUALITY_MIN_MEANINGFUL_LEVELS
    )
    assert smooth_report["quality_medians"]["normalized_entropy"] >= (
        picker.DEPTH_QUALITY_MIN_NORMALIZED_ENTROPY
    )
    assert smooth_report["diagnostic_status"] == "continuous_detail"
    assert smooth_report["diagnostic_warnings"] == []
    assert smooth_report["content_heuristics_blocking"] is False
    assert (
        smooth_report["quality_thresholds"]["measurement_scope"]
        == "nonzero_foreground_only"
    )
    assert smooth_report["quality_thresholds"]["blocking"] is False

    def recovered_proxy_preview(
        result: dict,
        _color: dict,
        depth: dict,
    ) -> None:
        evidence = {
            "candidate_shape_count": 1,
            "candidate_path_count": 2,
            "recovered_shape_count": 1,
            "recovered_path_count": 2,
            "recovered_paths": [
                "|Set|BushA|BushShape",
                "|Set|BushB|BushShape",
            ],
            "source_paths": ["|Set|BushSource|BushShapeOrig"],
        }
        for report in (
            result["depth_range_report"],
            depth["depth_range_report"],
        ):
            report["proxy_preview_recovery"] = dict(evidence)
            report["proxy_preview_recovery"]["recovered_paths"] = list(
                evidence["recovered_paths"]
            )
            report["proxy_preview_recovery"]["source_paths"] = list(
                evidence["source_paths"]
            )

    recovered_proxy_report = validate(
        smooth_color,
        smooth_depth,
        mutate=recovered_proxy_preview,
    )
    assert recovered_proxy_report["validated"] is True

    # Pixel-content heuristics are diagnostic only. These structurally valid
    # shader frames must publish, while still exposing useful candidate labels.
    for name, generator, expected_status in (
        ("binary mask", binary_depth_value, "mask_like_candidate"),
        (
            "four-level posterized depth",
            posterized_depth_value,
            "posterized_candidate",
        ),
        ("random noise", noise_depth_value, "irregular_candidate"),
    ):
        color_paths, depth_paths = write_fixture_frames(
            fixture_root,
            name.replace(" ", "_"),
            generator,
        )
        diagnostic_report = validate(color_paths, depth_paths)
        assert diagnostic_report["validated"] is True, name
        assert diagnostic_report["diagnostic_status"] == expected_status, name
        assert diagnostic_report["diagnostic_warnings"], name
        assert diagnostic_report["content_heuristics_blocking"] is False, name

    # Flat, sparse, and empty views are all valid results for arbitrary Maya
    # scenes. They are classified without pretending that pixels alone can
    # distinguish a flat surface from a segmentation mask.
    for name, generator, expected_status in (
        ("flat card", flat_depth_value, "flat_depth"),
        ("sparse object", sparse_depth_value, "sparse_unrated"),
        ("no visible geometry", no_visible_depth_value, "no_visible_depth"),
    ):
        color_paths, depth_paths = write_fixture_frames(
            fixture_root,
            name.replace(" ", "_"),
            generator,
        )
        valid_report = validate(color_paths, depth_paths)
        assert valid_report["validated"] is True, name
        assert valid_report["diagnostic_status"] == expected_status, name
        assert valid_report["quality_passed_frames"] == FRAME_COUNT, name
        assert valid_report["diagnostic_warnings"] == [], name

    def mismatch_frame_map(result: dict, _color: dict, depth: dict) -> None:
        depth["frame_map"][3]["maya_frame"] += 0.5

    assert_rejected(
        "mismatched frame map",
        lambda: validate(smooth_color, smooth_depth, mutate=mismatch_frame_map),
        "frame_map",
    )

    def mismatch_timing(_result: dict, _color: dict, depth: dict) -> None:
        depth["fps"] = 23.976

    assert_rejected(
        "mismatched timing",
        lambda: validate(smooth_color, smooth_depth, mutate=mismatch_timing),
        "FPS",
    )

    required_semantic_mutations = (
        ("space", "world", "space"),
        ("source", "samplerInfo.pointCameraZ", "source"),
        (
            "assignment_mode",
            "samplerInfo_shader_network",
            "assignment_mode",
        ),
        (
            "depth_update_scope",
            "single_setup_assignment",
            "depth_update_scope",
        ),
        (
            "representative_depth",
            "object_origin_camera_depth",
            "representative_depth",
        ),
        ("shader_model", "lambert", "shader_model"),
        ("direction", "near_black_far_white", "direction"),
        ("background", "scene_background", "background"),
        (
            "temporal_normalization",
            "per_frame_dynamic",
            "temporal_normalization",
        ),
        ("encoding_curve", "linear", "encoding_curve"),
        ("contrast_exponent", 0.25, "contrast exponent"),
        ("grayscale_bucket_count", 255, "256 grayscale buckets"),
        (
            "standard_nodes",
            ["samplerInfo", "surfaceShader"],
            "surfaceShader path",
        ),
        (
            "range_evaluation_scope",
            "sampled_subset",
            "complete requested sequence",
        ),
        (
            "range_evaluated_frame_count",
            FRAME_COUNT - 1,
            "evaluated frame count",
        ),
    )
    for field, invalid_value, expected_fragment in required_semantic_mutations:
        def mismatch_semantics(
            result: dict,
            _color: dict,
            depth: dict,
            *,
            field: str = field,
            invalid_value: object = invalid_value,
        ) -> None:
            for report in (
                result["depth_range_report"],
                depth["depth_range_report"],
            ):
                report[field] = invalid_value

        assert_rejected(
            f"mismatched {field}",
            lambda mismatch_semantics=mismatch_semantics: validate(
                smooth_color,
                smooth_depth,
                mutate=mismatch_semantics,
            ),
            expected_fragment,
        )

    def remove_proxy_recovery(
        result: dict,
        _color: dict,
        depth: dict,
    ) -> None:
        result["depth_range_report"].pop("proxy_preview_recovery")
        depth["depth_range_report"].pop("proxy_preview_recovery")

    assert_rejected(
        "missing proxy preview recovery evidence",
        lambda: validate(
            smooth_color,
            smooth_depth,
            mutate=remove_proxy_recovery,
        ),
        "proxy preview recovery evidence",
    )

    def incomplete_proxy_recovery(
        result: dict,
        _color: dict,
        depth: dict,
    ) -> None:
        for report in (
            result["depth_range_report"],
            depth["depth_range_report"],
        ):
            report["proxy_preview_recovery"].update({
                "candidate_shape_count": 1,
                "candidate_path_count": 1,
            })

    assert_rejected(
        "incomplete proxy preview recovery",
        lambda: validate(
            smooth_color,
            smooth_depth,
            mutate=incomplete_proxy_recovery,
        ),
        "proxy preview recovery is incomplete",
    )

    def remove_assignment_verification(
        result: dict,
        _color: dict,
        depth: dict,
    ) -> None:
        result["depth_range_report"].pop("assignment_verification")
        depth["depth_range_report"].pop("assignment_verification")

    assert_rejected(
        "missing shader assignment verification",
        lambda: validate(
            smooth_color,
            smooth_depth,
            mutate=remove_assignment_verification,
        ),
        "assignment verification evidence",
    )

    def incomplete_assignment_verification(
        result: dict,
        _color: dict,
        depth: dict,
    ) -> None:
        for report in (
            result["depth_range_report"],
            depth["depth_range_report"],
        ):
            report["assignment_verification"][
                "verified_shape_path_count"
            ] = 1

    assert_rejected(
        "incomplete shader assignment verification",
        lambda: validate(
            smooth_color,
            smooth_depth,
            mutate=incomplete_assignment_verification,
        ),
        "assignment verification is inconsistent",
    )

    def incomplete_frame_assignment_verification(
        result: dict,
        _color: dict,
        depth: dict,
    ) -> None:
        for report in (
            result["depth_range_report"],
            depth["depth_range_report"],
        ):
            report["assignment_verification"][
                "verified_frame_assignment_count"
            ] -= 1

    assert_rejected(
        "incomplete per-frame shader assignment verification",
        lambda: validate(
            smooth_color,
            smooth_depth,
            mutate=incomplete_frame_assignment_verification,
        ),
        "assignment verification is inconsistent",
    )

    def remove_cutout_transparency(
        result: dict,
        _color: dict,
        depth: dict,
    ) -> None:
        result["depth_range_report"].pop("cutout_transparency")
        depth["depth_range_report"].pop("cutout_transparency")

    assert_rejected(
        "missing authored cutout-transparency evidence",
        lambda: validate(
            smooth_color,
            smooth_depth,
            mutate=remove_cutout_transparency,
        ),
        "cutout-transparency evidence",
    )

    invalid_cutout_mutations = (
        (
            "unsupported authored cutout policy",
            {"policy": "opaque_depth_override"},
            "policy",
        ),
        (
            "unverified authored cutout",
            {"verified_shape_path_count": 0},
            "evidence is inconsistent",
        ),
        (
            "incomplete authored cutout capture",
            {"captured_shape_path_count": 1},
            "does not cover every renderable shape path",
        ),
        (
            "ambiguous authored cutout",
            {"ambiguous_shape_path_count": 1},
            "evidence is inconsistent",
        ),
        (
            "unsupported authored cutout",
            {"unsupported_shape_path_count": 1},
            "evidence is inconsistent",
        ),
    )
    for label, replacements, expected_fragment in invalid_cutout_mutations:
        def mismatch_cutout(
            result: dict,
            _color: dict,
            depth: dict,
            *,
            replacements: dict = replacements,
        ) -> None:
            for report in (
                result["depth_range_report"],
                depth["depth_range_report"],
            ):
                report["cutout_transparency"].update(replacements)

        assert_rejected(
            label,
            lambda mismatch_cutout=mismatch_cutout: validate(
                smooth_color,
                smooth_depth,
                mutate=mismatch_cutout,
            ),
            expected_fragment,
        )

    invalid_range_mutations = (
        ("non-positive near", {"near": 0.0}, "near"),
        ("inverted depth range", {"near": 250.0, "far": 2.0}, "range"),
        ("non-positive near clip", {"camera_near_clip": 0.0}, "clip"),
        (
            "inverted camera clip range",
            {"camera_near_clip": 1000.0, "camera_far_clip": 0.1},
            "clip",
        ),
        (
            "depth range outside camera clip",
            {"near": 0.05, "far": 1001.0},
            "clip",
        ),
    )
    for label, replacements, expected_fragment in invalid_range_mutations:
        def mismatch_range(
            result: dict,
            _color: dict,
            depth: dict,
            *,
            replacements: dict = replacements,
        ) -> None:
            for report in (
                result["depth_range_report"],
                depth["depth_range_report"],
            ):
                report.update(replacements)

        assert_rejected(
            label,
            lambda mismatch_range=mismatch_range: validate(
                smooth_color,
                smooth_depth,
                mutate=mismatch_range,
            ),
            expected_fragment,
        )


def generated_depth_descriptor(profile: str) -> dict:
    return {
        "video_slot": 2,
        "source_video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
        "companion_of_video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
        "media_kind": picker.DEPTH_MEDIA_KIND,
        "video_role": "maya_depth_companion",
        "source_type_hint": picker.DEPTH_SOURCE_TYPE,
        "control_role_hint": picker.DEPTH_CONTROL_ROLE,
        "pair_run_id": "visual-contract-pair",
        "bundle_run_id": "visual-contract-pair",
        "depth_profile": profile,
    }


current_depth = generated_depth_descriptor(EXPECTED_PROFILE)
legacy_depth = generated_depth_descriptor(LEGACY_PROFILES[-1])

# Picker must still identify legacy generated media so replacement/cleanup does
# not leave an obsolete camera-space companion behind.
for legacy_profile in LEGACY_PROFILES:
    assert picker._is_generated_depth_video_item(
        generated_depth_descriptor(legacy_profile)
    )
assert picker._is_generated_depth_video_item(current_depth)
assert picker._resolve_generated_companion_slots(
    {
        "videos": [
            {
                "video_slot": picker.PRIMARY_COLOR_VIDEO_SLOT,
                "pair_run_id": "visual-contract-pair",
                "bundle_run_id": "visual-contract-pair",
            },
            legacy_depth,
        ],
        "slot_assignments": [],
        "snapshots": [],
        "slot_visibility": [],
    },
    depth_enabled=True,
    motion_guide_enabled=False,
) == (2, 0)

# HMBPrompt authority is stricter: only the validated current visual contract
# may drive downstream spatial prompting.
assert prompt._picker_video_claims_generated_depth(legacy_depth, 2)
assert not prompt._picker_video_is_generated_depth(
    legacy_depth,
    2,
    "visual-contract-pair",
)
assert prompt._picker_video_is_generated_depth(
    current_depth,
    2,
    "visual-contract-pair",
)


print("HMB Depth visual contract regression passed.")
