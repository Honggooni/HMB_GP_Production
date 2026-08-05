from __future__ import annotations

import atexit
import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RELEASE_VERSION = "0.5.13"
POLICY_VERSION = "2026-08-01.goal-final-authority.v2"
CONTRACT_SHA256 = "a17809e4103628c1b0ab0b96081f6325faf9d16703a5fac57ef7d1eaa7d043bf"
AGENT_POLICY_PATH_ENV = "HMB_AGENT_POLICY_PATH"
REQUIRE_EXTERNAL_POLICY_ENV = "HMB_REQUIRE_EXTERNAL_POLICY"

ALLOWLIST = (
    "__init__.py",
    "griptape-nodes-library.json",
    "pyproject.toml",
    "README.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "SBOM.spdx.json",
    "HMBAgentLibrary.py",
    "HMBImageAssetLibrary.py",
    "HMBPromptLibrary.py",
    "HMBSeedance20VideoGeneration.py",
    "HMBVideoPickerLibrary.py",
    "_hmb_common.py",
    "_hmb_screen_space.py",
    "widgets/HMBAgentLibraryWidget.js",
    "widgets/HMBImageAssetLibraryWidget.js",
    "widgets/HMBPromptLibraryScopedBindingWidget.js",
    "widgets/HMBVideoPickerCommandBridgeWidget_v032.js",
    "widgets/HMBVideoPickerLibraryWidget_v032.js",
    "resources/maya/HMB_Maya_Background_Preview.py",
    "resources/maya/HMB_Maya_Binding_Setup.py",
    "resources/maya/HMBVideoPicker_Maya_Guide.txt",
    "resources/picker/HMB_Marker_Catalog.json",
)
PYTHON_COMPILE_TARGETS = (
    "__init__.py",
    "HMBAgentLibrary.py",
    "HMBImageAssetLibrary.py",
    "HMBPromptLibrary.py",
    "HMBSeedance20VideoGeneration.py",
    "HMBVideoPickerLibrary.py",
    "_hmb_common.py",
    "_hmb_screen_space.py",
    "resources/maya/HMB_Maya_Background_Preview.py",
    "resources/maya/HMB_Maya_Binding_Setup.py",
)
ARCHIVES = (
    ("HMB_GP_Production", DIST / "HMB_GP_Production.zip"),
)
REPRODUCIBLE_ZIP_DATE_TIME = (2020, 1, 1, 0, 0, 0)
REPRODUCIBLE_ZIP_MODE = 0o100644
RELEASE_MANIFEST_PATH = DIST / "release-manifest.json"
RELEASE_CHECKSUMS_PATH = DIST / "SHA256SUMS"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_text_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def assert_safe_relative(path_text: str) -> None:
    path = PurePosixPath(path_text)
    if path.is_absolute() or ".." in path.parts or "\\" in path_text:
        raise AssertionError(f"Unsafe release path: {path_text}")


if len(ALLOWLIST) != 25 or len(set(ALLOWLIST)) != 25:
    raise AssertionError("The release allowlist must contain 25 unique files.")
for relative in ALLOWLIST:
    assert_safe_relative(relative)
    source = ROOT / Path(relative)
    if not source.is_file():
        raise FileNotFoundError(source)

manifest = json.loads((ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8"))
if manifest.get("name") != "HMB_GP_Production":
    raise AssertionError("Unexpected manifest library name.")
if manifest.get("metadata", {}).get("library_version") != RELEASE_VERSION:
    raise AssertionError("Manifest release version mismatch.")
if len(manifest.get("nodes", [])) != 5 or len(manifest.get("widgets", [])) != 5:
    raise AssertionError("Manifest must register exactly 5 nodes and 5 widgets.")
manifest_tags = set(manifest.get("metadata", {}).get("tags", []))
for required_tag in (
    "DepthV7",
    "CutoutAlphaPreservation",
    "MotionGuideV5",
    "BlendShapeFaceSemantics",
    "NurbsCurveControllerProvenance",
    "VisibleFaceLandmarks",
    "MouthCardInnerPatch",
    "KeyboardDeleteProtection",
    "InstantColorAssignment",
    "PromptAssetImageAddLock",
    "SingleWireReferenceImages",
    "SingleWireVideoReferences",
    "VolcengineArk",
    "DirectArkTransport",
    "SecureArkAPIKey",
    "ReferenceImageCapacity9",
    "VideoReferenceCapacity3",
    "AudioReferenceCapacity3",
    "ImmediateLocalMP4",
    "ResumableArkTask",
    "StreamingSignedDownload",
    "DownloadSSRFGuard",
    "TemporaryVideoPublication",
    "SeparateGriptapeCloudKey",
    "VolcengineTOSUpload",
    "SingleVideoPreview",
    "GetOnlyTaskRecovery",
    "AmbiguousSubmissionSafety",
    "PrivatePerUserMonthlyUsageLedger",
    "OfflineUsageQueue",
    "AtomicUsageLedger",
):
    if required_tag not in manifest_tags:
        raise AssertionError(
            f"Manifest release tag missing: {required_tag}"
        )
secret_settings = manifest.get("settings", [])[0].get("contents", {}).get(
    "secrets_to_register"
)
if secret_settings != {
    "ARK_API_KEY": "",
    "GT_CLOUD_API_KEY": "",
    "GT_CLOUD_BUCKET_ID": "",
    "TOS_ACCESS_KEY_ID": "",
    "TOS_SECRET_ACCESS_KEY": "",
    "TOS_BUCKET_NAME": "",
}:
    raise AssertionError(
        "Manifest must register exactly the empty Ark and storage secret placeholders."
    )
for record in (*manifest["nodes"], *manifest["widgets"]):
    registered_path = str(
        record.get("file_path") or record.get("file") or record.get("path") or ""
    )
    if registered_path and registered_path not in ALLOWLIST:
        raise AssertionError(f"Registered path is outside release allowlist: {registered_path}")
image_asset_manifest = next(
    item
    for item in manifest["nodes"]
    if item.get("class_name") == "HMBImageAssetLibrary"
)
if image_asset_manifest.get("metadata", {}).get("width") != 1400:
    raise AssertionError("HMBImageAssetLibrary final width must remain 1400.")
if image_asset_manifest.get("metadata", {}).get("height") != 1200:
    raise AssertionError("HMBImageAssetLibrary final height must remain 1200.")
video_picker_manifest = next(
    item
    for item in manifest["nodes"]
    if item.get("class_name") == "HMBVideoPickerLibrary"
)
if video_picker_manifest.get("metadata", {}).get("width") != 1400:
    raise AssertionError("HMBVideoPickerLibrary final width must remain 1400.")
if video_picker_manifest.get("metadata", {}).get("height") != 1200:
    raise AssertionError("HMBVideoPickerLibrary final height must remain 1200.")
seedance_manifest = next(
    (
        item
        for item in manifest["nodes"]
        if item.get("class_name") == "HMBSeedance20VideoGeneration"
    ),
    None,
)
if seedance_manifest is None:
    raise AssertionError("HMB Seedance Volcengine node is not registered.")
if seedance_manifest.get("file_path") != "HMBSeedance20VideoGeneration.py":
    raise AssertionError("HMB Seedance manifest source path mismatch.")
if seedance_manifest.get("metadata", {}).get("category") != "HMB_GP_Production":
    raise AssertionError("HMB Seedance manifest category mismatch.")
seedance_declarations = [
    *seedance_manifest.get("declarations", []),
    *seedance_manifest.get("metadata", {}).get("declarations", []),
]
if any(
    declaration.get("type") in {"model_usage", "model_provider_usage"}
    for declaration in seedance_declarations
    if isinstance(declaration, dict)
):
    raise AssertionError(
        "HMB Seedance must not pin a copied Standard model-usage snapshot."
    )
library_declarations = [
    *manifest.get("declarations", []),
    *manifest.get("metadata", {}).get("declarations", []),
]
if any(
    declaration.get("type") == "model_catalog"
    for declaration in library_declarations
    if isinstance(declaration, dict)
):
    raise AssertionError(
        "HMB Seedance must not pin a copied Standard model catalog."
    )

pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
if not re.search(rf'(?m)^version\s*=\s*"{re.escape(RELEASE_VERSION)}"\s*$', pyproject):
    raise AssertionError("pyproject release version mismatch.")
for dependency in (
    "httpx==0.28.1",
    "imageio-ffmpeg==0.6.0",
    "Pillow==12.3.0",
    "tos==2.9.2",
):
    if dependency not in pyproject:
        raise AssertionError(f"Missing pinned dependency: {dependency}")

changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
if not re.search(
    rf"(?m)^##\s+{re.escape(RELEASE_VERSION)}\s+(?:-|—)\s+\d{{4}}-\d{{2}}-\d{{2}}\s*$",
    changelog,
):
    raise AssertionError("Changelog release heading mismatch.")

sbom = json.loads((ROOT / "SBOM.spdx.json").read_text(encoding="utf-8"))
if sbom.get("name") != f"HMB_GP_Production-{RELEASE_VERSION}":
    raise AssertionError("SBOM document release version mismatch.")
if not str(sbom.get("documentNamespace") or "").endswith(
    f"/HMB_GP_Production/{RELEASE_VERSION}"
):
    raise AssertionError("SBOM document namespace release version mismatch.")
sbom_package = next(
    (
        item
        for item in sbom.get("packages", [])
        if item.get("SPDXID") == "SPDXRef-HMB-GP-Production"
    ),
    None,
)
if not sbom_package or sbom_package.get("versionInfo") != RELEASE_VERSION:
    raise AssertionError("SBOM package release version mismatch.")
httpx_package = next(
    (
        item
        for item in sbom.get("packages", [])
        if item.get("SPDXID") == "SPDXRef-httpx"
    ),
    None,
)
if not httpx_package or httpx_package.get("versionInfo") != "0.28.1":
    raise AssertionError("SBOM HTTPX 0.28.1 package is missing.")
if not any(
    relationship.get("spdxElementId") == "SPDXRef-HMB-GP-Production"
    and relationship.get("relationshipType") == "DEPENDS_ON"
    and relationship.get("relatedSpdxElement") == "SPDXRef-httpx"
    for relationship in sbom.get("relationships", [])
):
    raise AssertionError("SBOM HMB-to-HTTPX dependency relationship is missing.")
tos_package = next(
    (
        item
        for item in sbom.get("packages", [])
        if item.get("SPDXID") == "SPDXRef-volcengine-tos"
    ),
    None,
)
if not tos_package or tos_package.get("versionInfo") != "2.9.2":
    raise AssertionError("SBOM Volcengine TOS SDK 2.9.2 package is missing.")
if not any(
    relationship.get("spdxElementId") == "SPDXRef-HMB-GP-Production"
    and relationship.get("relationshipType") == "DEPENDS_ON"
    and relationship.get("relatedSpdxElement") == "SPDXRef-volcengine-tos"
    for relationship in sbom.get("relationships", [])
):
    raise AssertionError("SBOM HMB-to-TOS dependency relationship is missing.")

common_text = (ROOT / "_hmb_common.py").read_text(encoding="utf-8")
init_text = (ROOT / "__init__.py").read_text(encoding="utf-8")
readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
prompt_text = (ROOT / "HMBPromptLibrary.py").read_text(encoding="utf-8")
agent_text = (ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8")
guide_text = (ROOT / "resources/maya/HMBVideoPicker_Maya_Guide.txt").read_text(
    encoding="utf-8"
)
image_asset_text = (ROOT / "HMBImageAssetLibrary.py").read_text(encoding="utf-8")
seedance_text = (ROOT / "HMBSeedance20VideoGeneration.py").read_text(
    encoding="utf-8"
)
image_asset_widget_text = (
    ROOT / "widgets/HMBImageAssetLibraryWidget.js"
).read_text(encoding="utf-8")
picker_text = (ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8")
for anchor in (
    "class HMBSeedance20VideoGeneration(SuccessFailureNode):",
    'ARK_API_KEY_SECRET = "ARK_API_KEY"',
    'GT_CLOUD_API_KEY_SECRET = "GT_CLOUD_API_KEY"',
    'GT_CLOUD_BUCKET_ID_SECRET = "GT_CLOUD_BUCKET_ID"',
    'TOS_ACCESS_KEY_ID_SECRET = "TOS_ACCESS_KEY_ID"',
    'TOS_SECRET_ACCESS_KEY_SECRET = "TOS_SECRET_ACCESS_KEY"',
    'TOS_BUCKET_NAME_SECRET = "TOS_BUCKET_NAME"',
    "POST_REQUEST_TIMEOUT_SECONDS = 300.0",
    'ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"',
    'CREATE_TASK_PATH = "/contents/generations/tasks"',
    'USAGE_GENERATOR_ID = "HMBSeedance20VideoGeneration"',
    r'\\fin-rcomp1\Composite_Team\00.CompSource\Griptape_list',
    'SEEDANCE_2_0_MODEL_ID = "doubao-seedance-2-0-260128"',
    'SEEDANCE_2_0_FAST_MODEL_ID = "doubao-seedance-2-0-fast-260128"',
    'SEEDANCE_2_0_MINI_MODEL_ID = "doubao-seedance-2-0-mini-260615"',
    "MAX_REFERENCE_IMAGES = 9",
    "MAX_VIDEO_REFERENCES = 3",
    "MAX_REFERENCE_AUDIO = 3",
    'VIDEO_REFERENCES_PARAMETER = "VIDEO_REFERENCES"',
    'name="reference_images"',
    'type="list[str]"',
    '"list[ImageUrlArtifact]"',
    '"list[BytePlusVideoAssetReference]"',
    '"display_name": "Reference Videos"',
    'name="reference_audio"',
    "Disabled by default on new nodes.",
    'name=f"reference_video_{index}"',
    'type="VideoUrlArtifact"',
    "File(text).resolve()",
    "GriptapeCloudStorageDriver",
    "def _prepare_video_references_for_run(",
    "driver.upload_file(",
    "driver.delete_file(",
    'importlib.import_module("tos")',
    "def _create_tos_storage_context(",
    "def _upload_local_video_to_tos(",
    "client.put_object_from_file(",
    "client.pre_signed_url(",
    "ParameterButton(",
    'name="generation_refresh"',
    'label="Refresh / Retrieve Result"',
    'allowed_modes={ParameterMode.PROPERTY}',
    'name="VIDEO_OUT"',
    'retry_allowed = retry and method in {"GET", "HEAD", "OPTIONS"}',
    "except httpx.RequestError as exc:",
    '"submission_unknown"',
    "def _list_ambiguous_submission_candidates(",
    "GriptapeNodes.SecretsManager().get_secret(ARK_API_KEY_SECRET)",
    "async def _request_json(",
    "async def _download_video(",
    "def _prepare_media_reference(",
    "async def _process_generation(",
    "async def _process_generation_impl(",
    "def _capture_usage_identity(",
    "def _enqueue_usage_event(",
    "def _write_usage_event_to_share(",
    "def _flush_usage_queue(",
    "def _record_usage_task(",
    "async def aprocess(self) -> None:",
    'name="auto_publish_local_videos"',
    'name="resume_generation_id"',
    '"Resume Task ID"',
    "async with client.stream(",
    "async def _validate_download_url(",
    "socket.getaddrinfo(",
    'if params["model_id"] == SEEDANCE_2_0_MODEL_ID:',
    '"POST",',
    '"GET", poll_path',
    'self.parameter_output_values["VIDEO_OUT"] = artifact',
    "VideoUrlArtifact(value=saved.location, name=saved.name)",
):
    if anchor not in seedance_text:
        raise AssertionError(f"HMB Seedance Volcengine anchor missing: {anchor}")
for forbidden_legacy_transport in (
    "_BaseSeedance20",
    "GriptapeProxyNode",
    "ProxyAuthProviderParameter",
    "HMB_GRIPTAPE_STANDARD_LIBRARY_PATH",
    "griptape_nodes_library/video/seedance_2_0_video_generation.py",
):
    if forbidden_legacy_transport in seedance_text:
        raise AssertionError(
            "HMB Seedance legacy Standard transport remains: "
            f"{forbidden_legacy_transport}"
        )
if 'SEEDANCE_2_0_MODEL_ID: ("480p", "720p", "1080p", "4k")' not in seedance_text:
    raise AssertionError(
        "HMB Seedance Standard must expose the verified Volcengine Ark 4k option."
    )
for restricted_resolution_contract in (
    'SEEDANCE_2_0_FAST_MODEL_ID: ("480p", "720p")',
    'SEEDANCE_2_0_MINI_MODEL_ID: ("480p", "720p")',
):
    if restricted_resolution_contract not in seedance_text:
        raise AssertionError(
            "HMB Seedance Fast/Mini resolution restriction is missing: "
            + restricted_resolution_contract
        )
seedance_tree = ast.parse(seedance_text, filename="HMBSeedance20VideoGeneration.py")
seedance_class = next(
    (
        node
        for node in seedance_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "HMBSeedance20VideoGeneration"
    ),
    None,
)
if seedance_class is None:
    raise AssertionError("HMB Seedance Volcengine class is missing.")
seedance_init = next(
    (
        node
        for node in seedance_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    ),
    None,
)
if seedance_init is None:
    raise AssertionError("HMB Seedance constructor is missing.")


def call_keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next(
        (keyword.value for keyword in call.keywords if keyword.arg == name),
        None,
    )


reference_image_calls = []
for call in (node for node in ast.walk(seedance_init) if isinstance(node, ast.Call)):
    parameter_name = call_keyword(call, "name")
    if not (
        isinstance(parameter_name, ast.Constant)
        and parameter_name.value == "reference_images"
    ):
        continue
    function_name = call.func.id if isinstance(call.func, ast.Name) else ""
    reference_image_calls.append((function_name, call))
if len(reference_image_calls) != 1 or reference_image_calls[0][0] != "Parameter":
    raise AssertionError(
        "HMB Seedance reference_images must be exactly one generic list Parameter."
    )
reference_image_call = reference_image_calls[0][1]
reference_image_type = call_keyword(reference_image_call, "type")
reference_image_input_types = call_keyword(reference_image_call, "input_types")
reference_image_hide_property = call_keyword(reference_image_call, "hide_property")
if not (
    isinstance(reference_image_type, ast.Constant)
    and reference_image_type.value == "list[str]"
    and isinstance(reference_image_input_types, (ast.List, ast.Tuple))
    and "list[str]"
    in {
        item.value
        for item in reference_image_input_types.elts
        if isinstance(item, ast.Constant)
    }
    and isinstance(reference_image_hide_property, ast.Constant)
    and reference_image_hide_property.value is True
):
    raise AssertionError(
        "HMB Seedance reference_images single-wire list[str] contract is incomplete."
    )
seedance_methods = {
    node.name
    for node in seedance_class.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
for required_method in (
    "_get_parameters",
    "_validate_parameters",
    "validate_before_node_run",
    "_build_payload",
    "_process_generation",
    "_process_generation_impl",
    "_request_json",
    "_download_video",
    "aprocess",
    "_capture_usage_identity",
    "_enqueue_usage_event",
    "_write_usage_event_to_share",
    "_flush_usage_queue",
    "_record_usage_task",
):
    if required_method not in seedance_methods:
        raise AssertionError(
            f"HMB Seedance direct implementation method missing: {required_method}"
        )
for anchor in (
    "from .HMBSeedance20VideoGeneration import HMBSeedance20VideoGeneration",
    '"HMBSeedance20VideoGeneration"',
):
    if anchor not in init_text:
        raise AssertionError(f"HMB Seedance package export missing: {anchor}")
for anchor in (
    "**Private repository only.**",
    "Do not make the GitHub repository or release assets public",
):
    if anchor not in readme_text:
        raise AssertionError(f"Private repository warning missing: {anchor}")
for anchor in (
    'get_library_info_by_library_name(',
    'LibraryRegistry.get_library("Griptape Nodes Library")',
    'library.get_node_class("Agent")',
    'griptape_nodes_library/agents/agent.py',
):
    if anchor not in common_text:
        raise AssertionError(f"Registered Standard Agent loader contract missing: {anchor}")
for forbidden_loader_pattern in (
    "Path.home(",
    ".rglob(",
    "pkgutil.walk_packages",
    "_registered_sibling_standard_library_root",
):
    if forbidden_loader_pattern in common_text:
        raise AssertionError(
            f"Unregistered Standard Agent search path remains: {forbidden_loader_pattern}"
        )
for anchor in (
    '"display_name": "PROMPT OUT"',
    '"hide_property": True',
):
    if anchor not in prompt_text:
        raise AssertionError(f"PROMPT_OUT port-only UI contract missing: {anchor}")
if 'current_ui.pop("hide_property"' in prompt_text:
    raise AssertionError("PROMPT_OUT repair must preserve hide_property=True.")
for anchor in (
    'display_name="PICKER OUT"',
    'def _configure_compact_output(',
    '"hide_property": True',
):
    if anchor not in picker_text:
        raise AssertionError(f"PICKER_OUT port-only UI contract missing: {anchor}")
for legacy_name in (
    "FINAL_MOTION_LOOK_POLICY_CLAUSES",
    "VIDEO_APPEARANCE_ISOLATION_CLAUSES",
    "GENERATOR_SOURCE_AUTHORITY_CONTRACT",
    "_VIDEO_APPEARANCE_ISOLATION_FALLBACK",
):
    if legacy_name in common_text or legacy_name in prompt_text:
        raise AssertionError(f"Plaintext policy source binding remains: {legacy_name}")
if "ColorPlayblastProxyAppearanceScope" not in manifest.get("metadata", {}).get("tags", []):
    raise AssertionError("Color Playblast proxy-appearance-scope release tag is missing.")
if "TypedAuxiliaryVideoAssets" not in manifest.get("metadata", {}).get("tags", []):
    raise AssertionError("Typed auxiliary video-asset release tag is missing.")
for composition_tag in (
    "IndependentLibraryOperation",
    "ComposableHybridWorkflow",
    "SubsetSafeAutomation",
    "FullFourLibraryAutomation",
    "All15LibraryCombinations",
    "OptionalSourceConnections",
    "GoalFirstGeneration",
    "NoConnectionPrerequisites",
    "PromptFourModes",
    "CanonicalPromptParent",
    "ExactPromptEdgeAgentPolicy",
    "NativeAgentWithoutHMBPrompt",
    "CanonicalHMBPolicyFailClosed",
):
    if composition_tag not in manifest.get("metadata", {}).get("tags", []):
        raise AssertionError(f"Hybrid composition release tag is missing: {composition_tag}")
if prompt_text.count('"input_types": ["any"]') < 2:
    raise AssertionError("Both Prompt source inputs must retain the official any wildcard.")
for anchor in (
    "Prompt only, Prompt + IMAGE_ASSET_IN, Prompt + PICKER_IN",
    "PROMPT_OUT is available in every mode",
    "_append_unconsumed_connected_fields",
    "_append_unconsumed_connected_rows",
):
    if anchor not in prompt_text:
        raise AssertionError(f"Canonical four-mode Prompt contract missing: {anchor}")
for anchor in (
    "def _is_direct_hmb_prompt_library_connection(",
    "type(source_node) is not expected_class",
    "_HMB_PROMPT_OUTPUT_PARAMETER",
    "is_hmb = self._has_canonical_hmb_prompt_connection()",
    "_HMB_POLICY_UNAVAILABLE_MESSAGE",
    "raise RuntimeError(_HMB_POLICY_UNAVAILABLE_MESSAGE)",
):
    if anchor not in agent_text:
        raise AssertionError(f"Canonical Prompt-to-Agent edge contract missing: {anchor}")
if "is_hmb = _is_hmb_prompt_library_payload(prompt)" in agent_text:
    raise AssertionError("Agent activation must not depend on copied Prompt text.")
if "continuing with the native Agent" in agent_text:
    raise AssertionError("Canonical HMB policy failure must not run the native Agent.")
for anchor in (
    "Every active video slot is independent",
    "Missing optional metadata or bindings never invents data",
    "SOURCE DATA WARNINGS:",
    "Every supplied source and the user goal remain independently usable",
):
    if anchor not in prompt_text:
        raise AssertionError(f"Prompt goal-first composition anchor missing: {anchor}")
for anchor in (
    "Mask / Color Assignment goal-first usage guidance (English)",
    "Mask / Color Assignment 목표 우선 사용 안내 (한글)",
    "Connecting any source adds available evidence only",
    "Original, Mask, Depth, Motion Guide, imported videos",
    "Any selected video may be connected and used",
):
    if anchor not in guide_text:
        raise AssertionError(f"Guide goal-first composition anchor missing: {anchor}")
for weak_allowance in (
    "Decode and use those pixels only",
    "Connected pixels are control evidence only",
):
    if weak_allowance in prompt_text or weak_allowance in guide_text:
        raise AssertionError(
            f"Weak Color Playblast pixel allowance remains: {weak_allowance}"
        )
for forbidden_goal_gate in (
    "Final prompt generation is blocked",
    "requires one validated Motion Guide",
    "mandatory downstream exact-alignment",
    "Generator exposure prohibited",
    "must not be connected, passed, exposed",
    "Do not connect @video1",
    "[HMB VALIDATION ERROR]",
    "_PROHIBITED_GLOBAL_CONTROL_",
    "exact local tuple authority is unverified",
    "full-shot/global Target wording",
    "full-shot/global Boundary wording",
):
    if (
        forbidden_goal_gate in prompt_text
        or forbidden_goal_gate in guide_text
        or forbidden_goal_gate
        in json.dumps(manifest, ensure_ascii=False)
    ):
        raise AssertionError(
            f"Connection-triggered creative gate remains: {forbidden_goal_gate}"
        )
for forbidden_release_text in (
    "03_Short_Prompt_Template_Final",
    "HMB_GP_Production_ReRender.zip",
):
    for relative in ALLOWLIST:
        if forbidden_release_text.encode("utf-8") in (ROOT / relative).read_bytes():
            raise AssertionError(
                f"Forbidden release text exposed in {relative}: "
                f"{forbidden_release_text}"
            )
for anchor in (
    'DEFAULT_PROJECTS_ROOT = Path(',
    "ASSET_NODE_WIDTH = 1400",
    "ASSET_NODE_HEIGHT = 1200",
    'IMAGE_IMPORT_PARAMETER = "IMAGE_IMPORT_IN"',
    'MEDIA_OUTPUT_PARAMETER = "IMAGE_OUT"',
    "def _discover_project_catalog(",
    "def _project_uid_from_id(",
    "def _match_catalog_project(",
    "def _asset_thumbnail_url(",
    "def _asset_manifest_process_lock(",
    "def _asset_manifest_signature(",
    "ASSET_METADATA_DIRECTORY_NAME = \".json\"",
    "def _apply_asset_registration(",
    "def _registration_folder_path(",
    "def _resolve_import_file_reference(",
    "def _copy_import_to_project(",
    "def _write_asset_manifest_record(",
    "def _disconnect_import_connection(",
    "DeleteConnectionRequest",
    '"disconnect_import_uid"',
    '"import_source_uid"',
    '"language": "en"',
    "OUTPUT_VERSION = 4",
    '"ordered_images": ordered_images',
    '"verified_assets": verified_assets',
    '"imported_images": imported_images',
    "def _resolve_selected_assets(",
    "def _build_synchronized_outputs(",
    '"media_resolution": {',
    "has no resolvable media and was omitted from both ASSET_OUT and ",
    '"Video Generation Out."',
    '"output_type": "list[str]"',
):
    if anchor not in image_asset_text:
        raise AssertionError(f"Image Asset runtime anchor missing: {anchor}")
for anchor in (
    "SELECTED IMAGES / GENERATOR ORDER",
    "Image + available metadata",
    "isUserImportFolder",
    "function hmbMoveSelectedAsset(",
    "function hmbPrepareImageAssetCanvasGestures(",
    "asset_registration_request",
    "data-project-set",
    "openNativeProjectRootPicker",
    "data-project-reload",
    "data-language-toggle",
    "toolbar-status",
    "hmbImageAssetStatusSummary",
    'data-count-digits="4"',
    "data-asset-view-toggle",
    "asset_view_mode",
    "state.disconnect_import_uid = asset.source_uid",
    'unclassified: "미분류 (선택 사항)"',
    "IMAGE_ASSET_UI_TEXT",
    "IMAGE_ASSET_AUTO_SYNC_MS = 10000",
    "__hmb_manifest_poll_nonce",
    "thumbnail_url",
    "data-asset-add",
    "data-registration-folder",
    'key: "$imports"',
    "MAX_SELECTED_IMAGES = 50",
    "ASSET PASSPORT",
    "flex-basis:120px",
    "height:118px",
):
    if anchor not in image_asset_widget_text:
        raise AssertionError(f"Image Asset widget anchor missing: {anchor}")
for removed_anchor in (
    "PROJECT_SET_SCHEMA",
    "_load_project_set",
    "_save_project_set",
    "_ensure_project_default_folders",
    "project_set_request",
):
    if removed_anchor in image_asset_text or removed_anchor in image_asset_widget_text:
        raise AssertionError(f"Removed Project Set feature returned: {removed_anchor}")
for anchor in (
    "def _remap_image_source_references_in_state(",
    '"ordered_source_uids": [',
    '"order_managed": True',
    "def _active_image_rows_for_state(",
    '"dormant_manual_rows": manual_cache',
    '"dormant_asset_rows": asset_cache',
    "Deselecting does not destroy authored fields",
    "IMAGE_ASSET_IN temporarily owns the visible @image slots",
):
    if anchor not in prompt_text:
        raise AssertionError(f"Prompt Image Asset ordering anchor missing: {anchor}")

marker_catalog = json.loads(
    (ROOT / "resources/picker/HMB_Marker_Catalog.json").read_text(encoding="utf-8")
)
if len(marker_catalog.get("character", [])) != 7:
    raise AssertionError("Preset Actor must contain 7 entries.")
if len(marker_catalog.get("background", [])) != 7:
    raise AssertionError("Preset Object must contain 7 entries.")
if marker_catalog["background"][-1].get("name") != "Position Pattern":
    raise AssertionError("Preset Object 7 must remain Position Pattern.")

screen_space_text = (ROOT / "_hmb_screen_space.py").read_text(encoding="utf-8")
for anchor in (
    'PROFILE = "hmb_screen_space_pattern_post_v2"',
    "PATTERN_LINEAR_SCALE_DIVISOR = 3",
    "SCALED_CELL_DIVISOR = BASE_CELL_DIVISOR * PATTERN_LINEAR_SCALE_DIVISOR",
    "POSITION_PATTERN_REPEATS = PATTERN_LINEAR_SCALE_DIVISOR",
):
    if anchor not in screen_space_text:
        raise AssertionError(f"Screen-space one-third-scale anchor missing: {anchor}")

picker_text = (ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8")
agent_widget_text = (
    ROOT / "widgets/HMBAgentLibraryWidget.js"
).read_text(encoding="utf-8")
picker_widget_text = (
    ROOT / "widgets/HMBVideoPickerLibraryWidget_v032.js"
).read_text(encoding="utf-8")
prompt_widget_text = (
    ROOT / "widgets/HMBPromptLibraryScopedBindingWidget.js"
).read_text(encoding="utf-8")
for label, widget_text in (
    ("Agent", agent_widget_text),
    ("Image Asset", image_asset_widget_text),
    ("Prompt", prompt_widget_text),
    ("Video Picker", picker_widget_text),
):
    for anchor in (
        "export function hmbGuardSelectedNodeKeyboardDelete(container, event)",
        'data-hmb-node-delete-protected", "true',
        'stopImmediatePropagation?.()',
    ):
        if anchor not in widget_text:
            raise AssertionError(f"{label} keyboard delete protection missing: {anchor}")
for anchor in (
    "export function hmbCanAddPromptImageRow(state, images = state?.images)",
    "!Boolean(state?.image_asset?.enabled)",
    'data-asset-locked="${assetLocked ? "true" : "false"}"',
    "if (!hmbCanAddPromptImageRow(state)) return;",
):
    if anchor not in prompt_widget_text:
        raise AssertionError(f"Prompt Asset image-add lock missing: {anchor}")
if 'id="apply-color"' in picker_widget_text or 'class="selected-target"' in picker_widget_text:
    raise AssertionError("Redundant Picker Target/APPLY row remains.")
if 'if (selectedNode) applyColor(color)' not in picker_widget_text:
    raise AssertionError("Picker palette must keep immediate color assignment.")
maya_runner_text = (
    ROOT / "resources/maya/HMB_Maya_Background_Preview.py"
).read_text(encoding="utf-8")
for label, text_value in (
    ("Picker", picker_text),
    ("Maya runner", maya_runner_text),
):
    if 'temporary_mouth_alpha_inner_patch_v1' not in text_value:
        raise AssertionError(
            f"{label} mouth-card inner-patch policy anchor is missing."
        )
for anchor in (
    "class _MouthCardInnerPatchController(object):",
    "Depth refused an opaque fallback for a mouth alpha card.",
    "post_frame_callback=mouth_controller.restore_frame",
):
    if anchor not in maya_runner_text:
        raise AssertionError(f"Maya mouth-card safety anchor missing: {anchor}")

# Picker notifications are log-only.  A footer/overlay regression can cover the
# whole node when Maya returns a long per-DAG diagnostic, so forbid those legacy
# surfaces and require the bounded, severity-aware Activity Log presentation.
for forbidden_picker_notification_surface in (
    'class="statusbar"',
    ".statusbar{",
    'class="warnings"',
    ".warnings{",
):
    if forbidden_picker_notification_surface in picker_widget_text:
        raise AssertionError(
            "Picker footer/overlay notification surface returned: "
            f"{forbidden_picker_notification_surface}"
        )
for anchor in (
    'id="activity-log-view" class="activity-log-view" role="log" aria-live="polite"',
    '.activity-log-row[data-level="ERROR"]{color:#fb7185}',
    "function hmbStateWithNotificationsLogged(",
):
    if anchor not in picker_widget_text:
        raise AssertionError(f"Picker log-only notification anchor missing: {anchor}")

# The complete Motion Guide report is a sidecar artifact.  Widget state and
# PICKER_OUT must carry only the bounded semantic/count summary, including the
# no-loss fallback path, or a valid facial guide can expand state by megabytes.
for anchor in (
    "def _compact_motion_guide_report_for_state(",
    "def has_heavy_key(item: Any) -> bool:",
    '"motion_frames",',
    '"face_channels",',
    'report["face_semantics"] = face_summary',
    'report["targets"] = target_summaries',
    'report["motion_frames_in_sidecar"] = True',
    'report["target_details_in_sidecar"] = True',
    "def _compact_slot_recovery_fallback(",
):
    if anchor not in picker_text:
        raise AssertionError(f"Picker compact Motion state anchor missing: {anchor}")
if picker_text.count("_compact_motion_guide_report_for_state(") < 4:
    raise AssertionError(
        "Picker compact Motion helper must protect normalized state, fallback, "
        "publication, and PICKER_OUT paths."
    )

# Depth shader/range/cutout consumers must share one exact Maya surface filter.
# Merely filtering the late auxiliary scope is insufficient because the authored
# cutout snapshot is captured before Color and otherwise retains controllers.
maya_contract_tree = ast.parse(
    maya_runner_text,
    filename="resources/maya/HMB_Maya_Background_Preview.py",
    feature_version=(3, 11),
)


def release_function_node(name: str) -> ast.FunctionDef:
    node = next(
        (
            item
            for item in maya_contract_tree.body
            if isinstance(item, ast.FunctionDef) and item.name == name
        ),
        None,
    )
    if node is None:
        raise AssertionError(f"Maya Depth contract function missing: {name}")
    return node


depth_surface_helper = release_function_node("_depth_supported_surface_shapes")
exact_surface_whitelist = {"mesh", "nurbsSurface"}
helper_has_exact_whitelist = any(
    {
        element.value
        for element in collection.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }
    == exact_surface_whitelist
    and len(collection.elts) == len(exact_surface_whitelist)
    for collection in ast.walk(depth_surface_helper)
    if isinstance(collection, (ast.List, ast.Tuple, ast.Set))
)
if not helper_has_exact_whitelist:
    raise AssertionError(
        "Maya Depth surface helper must use the exact mesh/nurbsSurface whitelist."
    )
for consumer_name in (
    "_all_depth_renderable_shapes",
    "_authored_cutout_scope_shapes",
):
    consumer = release_function_node(consumer_name)
    if not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_depth_supported_surface_shapes"
        for node in ast.walk(consumer)
    ):
        raise AssertionError(
            f"Maya Depth surface filter is not applied in {consumer_name}."
        )
for anchor in (
    "PICKER_START_WIDTH = 1400",
    "PICKER_START_HEIGHT = 1200",
):
    if anchor not in picker_text:
        raise AssertionError(f"Picker start-size anchor missing: {anchor}")

# The Picker has exactly two public outputs: Prompt metadata and one ordered
# generator media list. Fixed VIDEO1_OUT..VIDEO10_OUT rows are migration input
# only and must be actively retired from saved nodes.
picker_contract_tree = ast.parse(picker_text, filename="HMBVideoPickerLibrary.py")
output_registrations: list[tuple[str, str]] = []
for candidate in ast.walk(picker_contract_tree):
    if not (
        isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Name)
        and candidate.func.id == "_add_output"
        and len(candidate.args) >= 3
    ):
        continue
    raw_name = candidate.args[1]
    if isinstance(raw_name, ast.Constant) and isinstance(raw_name.value, str):
        output_name = raw_name.value
    elif isinstance(raw_name, ast.Name) and raw_name.id == "VIDEO_OUTPUT_PARAMETER":
        output_name = "VIDEO_OUT"
    else:
        raise AssertionError("Picker output registration uses an unknown name expression.")
    raw_type = candidate.args[2]
    if not isinstance(raw_type, ast.Constant) or not isinstance(raw_type.value, str):
        raise AssertionError(f"Picker output {output_name} has no static type contract.")
    output_registrations.append((output_name, raw_type.value))
if output_registrations != [("PICKER_OUT", "str"), ("VIDEO_OUT", "list[str]")]:
    raise AssertionError(
        "Picker public outputs must be exactly PICKER_OUT:str and "
        f"VIDEO_OUT:list[str], got {output_registrations!r}."
    )
for anchor in (
    'MAX_SELECTED_VIDEOS = 10',
    'VIDEO_OUTPUT_PARAMETER = "VIDEO_OUT"',
    "def _add_picker_output(node: Any) -> None:",
    "def _add_video_output(node: Any) -> None:",
    "Register the sole ordered media-list output for the generator.",
    "def _remove_parameter(node: Any, name: str) -> None:",
    "def _retire_legacy_video_slot_outputs(node: Any) -> None:",
    "for slot in range(1, MAX_SELECTED_VIDEOS + 1):",
    '_remove_parameter(node, f"VIDEO{slot}_OUT")',
    "_add_picker_output(self)",
    "_add_video_output(self)",
    "_retire_legacy_video_slot_outputs(self)",
):
    if anchor not in picker_text:
        raise AssertionError(f"Picker two-output/catalog anchor missing: {anchor}")
if "def _remove_video_slot_outputs_above" in picker_text:
    raise AssertionError("Retired dynamic fixed-slot output truncation remains.")
for forbidden_display_video_anchor in (
    "DisplayVideo",
    "_connect_generated_display_videos",
    "CreateConnectionRequest",
):
    if forbidden_display_video_anchor in picker_text:
        raise AssertionError(
            "Picker must not auto-create DisplayVideo nodes or connections: "
            f"{forbidden_display_video_anchor}"
        )

for anchor in (
    "Normalize an unlimited video catalog and its bounded selection.",
    "Retained {len(selected)} catalog videos but limited the active ",
    "def _append_video_asset(state: Dict[str, Any], item: Dict[str, Any])",
    'uid = f"video-{uuid.uuid4().hex}"',
    'record["catalog_order"] = len(catalog) + 1',
    "catalog.append(record)",
    "def _append_selected_generation_videos(",
    "No prior catalog record is replaced or packed.",
    'item["companion_video_uid"] = mask_uid',
    'item["source_video_uid"] = mask_uid',
    "def _build_synchronized_video_outputs(",
    "Build Prompt metadata and generator media from one selected snapshot.",
    '"schema_version": 5',
    '"selected_video_count": len(videos_payload)',
    '"max_selected_videos": MAX_SELECTED_VIDEOS',
    '"catalog_video_count": len(',
    '"ordered_video_uids": [',
    'video_payload["companion_video_uid"] = companion_uid',
    'video_payload["source_video_uid"] = companion_uid',
    "both PICKER_OUT and VIDEO_OUT",
):
    if anchor not in picker_text:
        raise AssertionError(f"Picker append-only stable-UID anchor missing: {anchor}")
for anchor in (
    "const HMB_DEFAULT_NODE_WIDTH = 1400;",
    "const HMB_DEFAULT_NODE_HEIGHT = 1200;",
):
    if anchor not in picker_widget_text:
        raise AssertionError(f"Picker Widget start-size anchor missing: {anchor}")
for label, source_text in (
    ("Picker", picker_text),
    ("Maya runner", maya_runner_text),
):
    for anchor in (
        'SCREEN_SPACE_PATTERN_PROFILE = "hmb_screen_space_pattern_post_v2"',
        "SCREEN_SPACE_PATTERN_LINEAR_SCALE_DIVISOR = 3",
    ):
        if anchor not in source_text:
            raise AssertionError(
                f"{label} one-third-scale contract anchor missing: {anchor}"
            )

for anchor in (
    'DEPTH_PLAYBLAST_PROFILE = "hmb_camera_space_depth_v7"',
    "LEGACY_DEPTH_PLAYBLAST_PROFILES = frozenset({",
    '"hmb_camera_space_depth_v4",',
    '"hmb_camera_space_depth_v5",',
    '"hmb_camera_space_depth_v6",',
    "DEPTH_NEAR_COLOR = 0.9",
    "DEPTH_CAMERA_NEAR_SAFETY_MARGIN = 0.1",
    "DEPTH_CONTRAST_EXPONENT = 1.0",
    "DEPTH_FOREGROUND_NEAR_PERCENTILE = 0.01",
    "DEPTH_FOREGROUND_FAR_PERCENTILE = 0.99",
    "DEPTH_GENERIC_FAR_PERCENTILE = 0.95",
    'DEPTH_REJECTION_ACCOUNTING_POLICY = "disjoint_normalization_outcomes"',
    "DEPTH_GRAYSCALE_CHANNEL_TOLERANCE = 2",
    '"preserve_authored_material_out_transparency_v1"',
    'range_report.get("cutout_transparency")',
    'shot_range_sample.get("rejection_accounting_policy")',
    'MOTION_GUIDE_PROFILE = "hmb_target_neutral_motion_guide_v5"',
    "LEGACY_MOTION_GUIDE_PROFILES = frozenset({",
    '"hmb_target_neutral_motion_guide_v4",',
    "MOTION_GUIDE_COMPATIBLE_PROFILES = frozenset({",
    "MOTION_GUIDE_RUNNER_SCHEMA_VERSION = 2",
    "MOTION_GUIDE_SIDECAR_SCHEMA_VERSION = 2",
    "MOTION_GUIDE_FACE_BROW_RGB = (176, 96, 255)",
    "MOTION_GUIDE_FACE_EYELID_RGB = (48, 196, 255)",
    "MOTION_GUIDE_FACE_MOUTH_RGB = (255, 72, 180)",
    "MOTION_GUIDE_FACE_JAW_RGB = (255, 176, 64)",
    "def _validate_depth_companion_inputs(",
    'range_report.get("proxy_preview_recovery")',
    'range_report.get("assignment_verification")',
    '"object_bbox_camera_depth"',
    '"color_picker_style_shared_gray_material_buckets"',
    '"per_shape_path_per_output_frame"',
    '"median_positive_camera_depth_of_world_bbox_corners"',
    'range_report.get("grayscale_bucket_count")',
    '"depth_of_field_disabled"',
    '"fog_disabled"',
    "def _validate_motion_guide_inputs(",
    "with _playblast_publish_guard(scene_path):",
    '"pair_run_id": pair_run_id',
    '"bundle_run_id": bundle_run_id',
    '"generate_motion_guide": motion_guide_enabled',
    "_validate_encoded_playblast(",
    "def _validated_runner_result_path(",
    "def _publish_validated_playblast_artifact(",
    "transaction_records=color_project_records",
    "transaction_records=depth_project_records",
    "transaction_records=motion_project_records",
    '"publish-backup" / "color"',
    '"publish-backup" / "depth"',
    '"publish-backup" / "motion"',
    '"project-publish-backup"',
    "source_bytes = path.read_bytes()",
    "FileDestination.write_bytes(",
    "def _is_allowed_project_create_new_path(",
    're.escape(planned_stem) + r"_0*[1-9][0-9]*"',
    "Griptape metadata resolver returned the media file itself.",
    # These numbers are private Maya one-pass staging positions only. Public
    # identity and Prompt/Generator relationships use stable video UIDs.
    "AUXILIARY_VIDEO_SLOTS = (2, 3, 4, 5)",
    "def _resolve_generated_companion_slots(",
    "depth_video_slot = context.depth_video_slot",
    "motion_guide_video_slot = context.motion_guide_video_slot",
    'ORIGINAL_MEDIA_KIND = "maya_original_playblast"',
    'MASK_MEDIA_KIND = "maya_color_assignment_mask"',
    "def _generation_choice_roles(",
    "def _append_selected_generation_videos(",
    "manual_source_state=pre_generation_state",
    'item["companion_video_uid"] = mask_uid',
    'item["source_video_uid"] = mask_uid',
    "def _mask_authoring_slot(",
    "publish_public=False",
):
    if anchor not in picker_text:
        raise AssertionError(f"Picker paired-Depth contract anchor missing: {anchor}")
if "import mmap" in picker_text or "mmap." in picker_text:
    raise AssertionError(
        "Picker project publication must pass real bytes to Griptape, not mmap."
    )
for anchor in (
    'PICKER_DEPTH_PROFILE = "hmb_camera_space_depth_v7"',
    'PICKER_MOTION_GUIDE_PROFILE = "hmb_target_neutral_motion_guide_v5"',
    "PICKER_LEGACY_MOTION_GUIDE_PROFILES = frozenset({",
    '"hmb_target_neutral_motion_guide_v4",',
    "PICKER_MOTION_GUIDE_PROFILES = frozenset({",
    "in PICKER_MOTION_GUIDE_PROFILES",
    "_PICKER_AUTO_DEPTH_FIELDS",
    "not expected_pair_run_id",
    "def _release_picker_generated_depth(",
    "def _release_picker_generated_motion_guide(",
    "def _invalidate_picker_generated_motion_guide(",
    "claimed_companion_slots = (",
    "generated_companion_slots = (",
    "claimed_motion_guide_slots",
    "generated_motion_guide_slots",
    "def _picker_companion_source_slot(",
    "def _picker_companion_expected_run_id(",
    "source_slot == 0",
    "int(slot or 0) not in range(1, MAX_VIDEOS + 1)",
    "Every active video slot is independent",
    "Missing optional metadata or bindings never invents data",
):
    if anchor not in prompt_text:
        raise AssertionError(f"Prompt typed-companion contract anchor missing: {anchor}")
for anchor in (
    "function normalizePickerAutoDepth(",
    "function normalizePickerAutoMotionGuide(",
    "picker_auto_depth: {}",
    "picker_auto_motion_guide: {}",
    "out.picker_auto_depth = normalizePickerAutoDepth(item.picker_auto_depth)",
    "out.picker_auto_motion_guide = normalizePickerAutoMotionGuide(",
):
    if anchor not in prompt_widget_text:
        raise AssertionError(f"Prompt Widget paired-Depth provenance anchor missing: {anchor}")
for anchor in (
    "const HMB_PICKER_MAX_SELECTED_VIDEOS = 10;",
    "export function hmbSelectedVideoAssets(state)",
    ".slice(0, HMB_PICKER_MAX_SELECTED_VIDEOS)",
    "function hmbApplyVideoAssetSelection(state, orderedUids",
    "export function hmbToggleVideoAssetSelection(state, uid)",
    "export function hmbMoveSelectedVideoAsset(state, uid, targetIndex)",
    "export function hmbPreviewVideoAsset(state, uid)",
    "export function hmbDeleteVideoAsset(state, uid)",
    "export function hmbSnapshotHistory(state)",
    "snapshot_uid: hmbSnapshotUid(item, snapshotIndex)",
    'active_snapshot_uid: ""',
    'viewport_mode: "video"',
    'data-video-uid="${escapeHtml(uid)}"',
    'data-selected-video-uid="${escapeHtml(uid)}"',
    'data-toggle-video-uid="${escapeHtml(uid)}"',
    'data-play-video-uid="${escapeHtml(uid)}"',
    'class="video-asset-play" data-play-video-uid="${escapeHtml(uid)}"',
    'preload="metadata" muted playsinline draggable="false" aria-hidden="true"',
    'class="video-asset-copy" data-toggle-video-uid="${escapeHtml(uid)}" role="button"',
    'tabindex="${blocked || locked ? "-1" : "0"}"',
    'aria-disabled="${blocked || locked ? "true" : "false"}"',
    'data-delete-video-uid="${escapeHtml(uid)}"',
    'draggable="true"',
    "if (leftOrder && rightOrder) return leftOrder - rightOrder;",
    "export function hmbInstallVideoAssetDragReorder(",
    "container.addEventListener(eventName, handler, true);",
    'finalize("drop")',
    'finalize("dragend")',
    'event?.target?.closest?.("[data-play-video-uid], [data-delete-video-uid]")',
    "container.__hmbSuppressVideoSelectionClick = true;",
    "delete container.__hmbDraggedVideoUid;",
    "hmbMoveSelectedVideoAsset(liveState, sourceUid, targetIndex)",
    "hmbApplySelectedVideoAssetOrderToDom(container, nextState)",
    ".video-asset-grid{display:grid",
    ".video-asset-grid{grid-template-columns:repeat(auto-fill,minmax(132px,1fr))}",
    ".video-asset-card.selected{border-width:2px;border-color:rgb(var(--selection-rgb));box-shadow:0 0 0 2px rgba(var(--selection-rgb),.82),0 0 28px rgba(var(--selection-rgb),.62)",
    'id="import-video-button"',
    'id="import-video-asset"',
    'dispatchCommand("import_video_asset"',
    'container.querySelectorAll("[data-play-video-uid]")',
    'const autoplayVideo = container.querySelector("#picker-video");',
    "autoplayVideo?.play?.()",
    "container.__hmbAutoplayVideoUid = uid;",
    "container.__hmbForceVideoPreviewUid = uid;",
    'commit({ ...hmbPreviewVideoAsset(liveState, uid), viewport_mode: "video" });',
    'selectionSurface.getAttribute("aria-disabled") === "true"',
    'on(selectionSurface, "keydown"',
    'if (!["Enter", " "].includes(event.key)) return;',
    'container.querySelector("#picker-video")?.pause?.();',
    "delete container.__hmbForceVideoPreviewUid;",
    "delete container.__hmbAutoplayVideoUid;",
    'id="picker-snapshot-image"',
    'id="picker-video"',
    'id="snapshot-prev"',
    'id="video-play-toggle"',
    'id="snapshot-next"',
    'const viewportModeLabel = snapshotForViewport ? (tr.snapshot || "Snapshot") : (tr.preview || "Video");',
    "const showAdjacentSnapshot = (direction) => {",
    'on(container.querySelector("#snapshot-prev"), "click", () => showAdjacentSnapshot(-1));',
    'on(container.querySelector("#snapshot-next"), "click", () => showAdjacentSnapshot(1));',
    'commit({ ...liveState, viewport_mode: "video" });',
    'video_uid: clean(currentLocal.preview_video_uid || currentLocal.selected_video_uid)',
    'snapshot_uid: clean(activeSnapshot.snapshot_uid)',
    ".video-asset-delete{top:7px;right:7px;bottom:auto",
    ".selected-video-order{top:auto;right:7px;bottom:7px}",
    'data-resize-section="color"',
    'container.querySelectorAll("[data-resize-section]")',
    'on(handle, "pointerdown"',
    ".video-assets-section>.section-resize-handle:before{display:none}",
    'importVideoAsset: "Load"',
    'TEXT.ko.importVideoAsset = "\\uAC80\\uC0C9";',
    'class="import-video-icon"',
    ".generate-button,.hmbvp[data-theme] .import-video-button{",
    "include_original: originalEnabled",
    "include_mask: maskEnabled",
    "include_motion_guide: motionGuideEnabled",
    'id="mask-playblast-toggle"',
    "const liveSlot = 1;",
):
    if anchor not in picker_widget_text:
        raise AssertionError(f"Picker Widget UID-catalog anchor missing: {anchor}")
for forbidden_lossy_drag_handler in (
    'on(card, "dragstart"',
    'on(card, "dragover"',
    'on(card, "drop"',
    'on(card, "dragend"',
):
    if forbidden_lossy_drag_handler in picker_widget_text:
        raise AssertionError(
            "Picker Widget retained a per-card bubble drag handler: "
            f"{forbidden_lossy_drag_handler}"
        )
picker_card_template_start = picker_widget_text.find("function videoAssetCardsHtml(")
picker_card_template_end = picker_widget_text.find(
    "export function hmbInstallPickerInteractionIsolation(",
    picker_card_template_start,
)
if picker_card_template_start < 0 or picker_card_template_end <= picker_card_template_start:
    raise AssertionError("Picker Widget current-cut card template boundaries are missing.")
picker_card_template = picker_widget_text[
    picker_card_template_start:picker_card_template_end
]
picker_play_control_tags = re.findall(
    r'<[^>]+data-play-video-uid="\$\{escapeHtml\(uid\)\}"[^>]*>',
    picker_card_template,
)
if not picker_play_control_tags or any(
    not re.match(r'<button\b[^>]*class="video-asset-play"(?:\s|>)', tag)
    for tag in picker_play_control_tags
):
    raise AssertionError(
        "Picker Widget data-play-video-uid must belong only to the centered button."
    )
if re.search(
    r'<div\b[^>]*class="video-asset-thumb"[^>]*data-play-video-uid=',
    picker_card_template,
):
    raise AssertionError(
        "Picker Widget thumbnail surface must remain available for card dragging."
    )
picker_thumbnail_media_tags = re.findall(
    r'<video\b[^>]*class="video-asset-thumb-media"[^>]*>',
    picker_card_template,
)
if not picker_thumbnail_media_tags or any(
    'draggable="false"' not in tag or re.search(r'\bautoplay\b', tag)
    for tag in picker_thumbnail_media_tags
):
    raise AssertionError(
        "Picker Widget thumbnail videos must remain static and non-draggable."
    )
for retired_card_markup in (
    "data-preview-video-uid=",
    " previewing",
    'class="video-asset-footer',
    'class="video-order-actions',
    "tr.previewLarge",
):
    if retired_card_markup in picker_card_template:
        raise AssertionError(
            "Picker Widget retired video-card markup remains: "
            f"{retired_card_markup}"
        )
for forbidden_inline_playback in (
    "const syncInlineVideoIndicator =",
    "toggleInlineVideo(",
    "media.play?.()",
    "media.pause?.()",
    "otherMedia.pause?.()",
):
    if forbidden_inline_playback in picker_widget_text:
        raise AssertionError(
            "Picker Widget thumbnail media playback remains: "
            f"{forbidden_inline_playback}"
        )
if ".video-asset-card.is-playing" in picker_widget_text:
    raise AssertionError(
        "Picker Widget inline playback must not add an outer card outline."
    )
picker_preview_handler_start = picker_widget_text.find(
    'container.querySelectorAll("[data-play-video-uid]")',
    picker_widget_text.find('on(container.querySelector("#import-video-asset"), "change"'),
)
picker_selection_handler_start = picker_widget_text.find(
    'container.querySelectorAll("[data-toggle-video-uid]")',
    picker_preview_handler_start,
)
picker_delete_handler_start = picker_widget_text.find(
    'container.querySelectorAll("[data-delete-video-uid]")',
    picker_selection_handler_start,
)
picker_drag_handler_start = picker_widget_text.find(
    "activeCleanup.push(hmbInstallVideoAssetDragReorder(",
    picker_delete_handler_start,
)
picker_resize_handler_start = picker_widget_text.find(
    'container.querySelectorAll("[data-resize-section]")',
    picker_drag_handler_start,
)
if not (
    0 <= picker_preview_handler_start
    < picker_selection_handler_start
    < picker_delete_handler_start
    < picker_drag_handler_start
    < picker_resize_handler_start
):
    raise AssertionError("Picker Widget video-card handler boundaries are missing.")
picker_preview_handler = picker_widget_text[
    picker_preview_handler_start:picker_selection_handler_start
]
for anchor in (
    'container.querySelector("#picker-video")',
    "container.__hmbAutoplayVideoUid = uid;",
    "container.__hmbForceVideoPreviewUid = uid;",
    'commit({ ...hmbPreviewVideoAsset(liveState, uid), viewport_mode: "video" });',
):
    if anchor not in picker_preview_handler:
        raise AssertionError(f"Picker main-preview routing anchor missing: {anchor}")
if re.search(
    r'video-asset-thumb-media|\bmedia\.play|\bmedia\.pause|\botherMedia\b',
    picker_preview_handler,
):
    raise AssertionError("Picker play control must never play thumbnail media.")
picker_selection_handler = picker_widget_text[
    picker_selection_handler_start:picker_delete_handler_start
]
for anchor in (
    "locked",
    'selectionSurface.getAttribute("aria-disabled") === "true"',
    "container.__hmbSuppressVideoSelectionClick",
    'on(selectionSurface, "click", toggleSelection)',
    'on(selectionSurface, "keydown"',
    'if (!["Enter", " "].includes(event.key)) return;',
):
    if anchor not in picker_selection_handler:
        raise AssertionError(f"Picker lower-copy selection anchor missing: {anchor}")
picker_delete_handler = picker_widget_text[
    picker_delete_handler_start:picker_drag_handler_start
]
picker_delete_dispatch = picker_delete_handler.find(
    'dispatchCommand("delete_video_asset"'
)
if picker_delete_dispatch < 0:
    raise AssertionError("Picker delete command dispatch anchor is missing.")
for cleanup in (
    'container.querySelector("#picker-video")?.pause?.();',
    "delete container.__hmbForceVideoPreviewUid;",
    "delete container.__hmbAutoplayVideoUid;",
):
    cleanup_index = picker_delete_handler.find(cleanup)
    if cleanup_index < 0 or cleanup_index >= picker_delete_dispatch:
        raise AssertionError(
            f"Picker active-preview cleanup must precede delete dispatch: {cleanup}"
        )
picker_drag_handler = picker_widget_text[
    picker_widget_text.find("export function hmbInstallVideoAssetDragReorder("):
    picker_widget_text.find(
        "export function hmbPreviewVideoAsset(",
        picker_widget_text.find("export function hmbInstallVideoAssetDragReorder("),
    )
]
expected_drag_guard = (
    'event?.target?.closest?.("[data-play-video-uid], [data-delete-video-uid]")'
)
if expected_drag_guard not in picker_drag_handler:
    raise AssertionError("Picker dragstart play/delete-only guard is missing.")
if "data-toggle-video-uid" in picker_drag_handler:
    raise AssertionError("Picker lower-copy selection surface must remain draggable.")
for anchor in (
    "container.addEventListener(eventName, handler, true);",
    "delete container.__hmbDraggedVideoUid;",
    "setTimeout(() => { delete container.__hmbSuppressVideoSelectionClick; }, 0);",
    "hmbMoveSelectedVideoAsset(liveState, sourceUid, targetIndex)",
    "hmbApplySelectedVideoAssetOrderToDom(container, nextState)",
    'finalize("drop")',
    'finalize("dragend")',
):
    if anchor not in picker_drag_handler:
        raise AssertionError(f"Picker delegated-drag anchor missing: {anchor}")
if picker_drag_handler.find("clearSession();") >= picker_drag_handler.find(
    "hmbApplySelectedVideoAssetOrderToDom(container, nextState)"
):
    raise AssertionError("Picker successful drag must release its latch before commit.")

for removed_viewport_contract in (
    'id="open-video"',
    'id="open-video-file"',
    "__hmbOpenedVideoUrl",
    "__hmbOpenedVideoName",
    "URL.createObjectURL",
    "URL.revokeObjectURL",
    'id="video-prev-frame"',
    'id="video-next-frame"',
):
    if removed_viewport_contract in picker_widget_text:
        raise AssertionError(
            "Picker retired viewport/Open contract remains: "
            f"{removed_viewport_contract}"
        )

picker_normalized_viewport_start = picker_widget_text.find(
    "const requestedViewportMode ="
)
picker_normalized_viewport_end = picker_widget_text.find(
    "state.viewport_mode = viewportMode;", picker_normalized_viewport_start
)
if (
    picker_normalized_viewport_start < 0
    or picker_normalized_viewport_end <= picker_normalized_viewport_start
):
    raise AssertionError("Picker backend viewport-mode normalization block is missing.")
picker_normalized_viewport = picker_widget_text[
    picker_normalized_viewport_start:
    picker_normalized_viewport_end + len("state.viewport_mode = viewportMode;")
]
for anchor in (
    "source?.viewport_mode",
    'state.snapshot_active && activeSnapshotUid ? "snapshot" : "video"',
    "state.viewport_mode = viewportMode;",
):
    if anchor not in picker_normalized_viewport:
        raise AssertionError(
            f"Picker backend snapshot-success mode anchor missing: {anchor}"
        )

picker_viewport_mode_start = picker_widget_text.find("const viewportMode =")
picker_force_video_start = picker_widget_text.find(
    "const forceVideoPreview", picker_viewport_mode_start
)
if picker_viewport_mode_start < 0 or picker_force_video_start <= picker_viewport_mode_start:
    raise AssertionError("Picker shared viewport-mode block is missing.")
picker_viewport_mode = picker_widget_text[
    picker_viewport_mode_start:picker_force_video_start
]
for anchor in (
    'viewportMode === "snapshot"',
    "retainedViewportVideo?.pause?.()",
    "delete container.__hmbAutoplayVideoUid",
    "delete container.__hmbForceVideoPreviewUid",
):
    if anchor not in picker_viewport_mode:
        raise AssertionError(f"Picker snapshot-mode override anchor missing: {anchor}")

picker_selected_snapshot_start = picker_widget_text.find("const selectedSnapshot =")
picker_initial_viewport_frame_start = picker_widget_text.find(
    "const initialViewportFrame", picker_selected_snapshot_start
)
if (
    picker_selected_snapshot_start < 0
    or picker_initial_viewport_frame_start <= picker_selected_snapshot_start
):
    raise AssertionError("Picker active snapshot selection block is missing.")
picker_selected_snapshot = picker_widget_text[
    picker_selected_snapshot_start:picker_initial_viewport_frame_start
]
for anchor in (
    "snapshotHistory.find(",
    "state.active_snapshot_uid",
    "snapshotHistory.at(-1)",
    'snapshotForViewport = viewportMode === "snapshot"',
):
    if anchor not in picker_selected_snapshot:
        raise AssertionError(f"Picker active snapshot viewport anchor missing: {anchor}")
if any(
    retired in picker_selected_snapshot
    for retired in ("previewOrder", "selectedSlot", "video_slot")
):
    raise AssertionError(
        "Picker snapshot viewport must not depend on a selected video slot."
    )

picker_snapshot_navigation_start = picker_widget_text.find(
    "const showAdjacentSnapshot ="
)
picker_main_transport_start = picker_widget_text.find(
    'on(playToggleButton, "click"', picker_snapshot_navigation_start
)
picker_main_transport_end = picker_widget_text.find(
    'on(videoSeekInput, "input"', picker_main_transport_start
)
if not (
    0 <= picker_snapshot_navigation_start
    < picker_main_transport_start
    < picker_main_transport_end
):
    raise AssertionError("Picker snapshot/video transport boundaries are missing.")
picker_snapshot_navigation = picker_widget_text[
    picker_snapshot_navigation_start:picker_main_transport_start
]
for anchor in (
    "hmbSnapshotHistory(liveState)",
    "liveState.active_snapshot_uid",
    "(activeIndex + step + liveHistory.length) % liveHistory.length",
    'viewport_mode: "snapshot"',
    "active_snapshot_uid: clean(target.snapshot_uid)",
    'on(container.querySelector("#snapshot-prev"), "click", () => showAdjacentSnapshot(-1))',
    'on(container.querySelector("#snapshot-next"), "click", () => showAdjacentSnapshot(1))',
):
    if anchor not in picker_snapshot_navigation:
        raise AssertionError(f"Picker circular snapshot navigation anchor missing: {anchor}")
picker_main_transport = picker_widget_text[
    picker_main_transport_start:picker_main_transport_end
]
for anchor in (
    "if (!viewportVideo)",
    "container.__hmbAutoplayVideoUid = livePreviewUid",
    'commit({ ...liveState, viewport_mode: "video" });',
    "viewportVideo.pause()",
    "viewportVideo.play?.()",
):
    if anchor not in picker_main_transport:
        raise AssertionError(f"Picker central video transport anchor missing: {anchor}")
if 'playToggleButton.textContent = playing ? "Ⅱ" : "▶"' not in picker_widget_text:
    raise AssertionError("Picker central transport play/pause glyph contract is missing.")

picker_snapshot_create_start = picker_widget_text.find(
    'on(container.querySelector("#create-snapshot")'
)
picker_snapshot_delete_start = picker_widget_text.find(
    'on(container.querySelector("#delete-snapshot")', picker_snapshot_create_start
)
picker_snapshot_delete_end = picker_widget_text.find(
    'on(container.querySelector("#run-video")', picker_snapshot_delete_start
)
if not (
    0 <= picker_snapshot_create_start
    < picker_snapshot_delete_start
    < picker_snapshot_delete_end
):
    raise AssertionError("Picker snapshot command handler boundaries are missing.")
picker_snapshot_create = picker_widget_text[
    picker_snapshot_create_start:picker_snapshot_delete_start
]
for anchor in (
    'dispatchCommand("render_snapshot"',
    "video_uid: clean(currentLocal.preview_video_uid || currentLocal.selected_video_uid)",
):
    if anchor not in picker_snapshot_create:
        raise AssertionError(f"Picker snapshot-create identity anchor missing: {anchor}")
picker_snapshot_delete = picker_widget_text[
    picker_snapshot_delete_start:picker_snapshot_delete_end
]
for anchor in (
    "hmbSnapshotHistory(currentLocal).find(",
    "currentLocal.active_snapshot_uid",
    'dispatchCommand("delete_snapshot"',
    "snapshot_uid: clean(activeSnapshot.snapshot_uid)",
):
    if anchor not in picker_snapshot_delete:
        raise AssertionError(f"Picker exact snapshot-delete anchor missing: {anchor}")
for retired_fixed_slot_helper in (
    "HMB_NATIVE_VIDEO_OUTPUT_ROW_HEIGHT",
    "function hmbPickerVideoOutputHandles(",
    "export function hmbPulsePickerOutputHandleMeasurement(",
    "export function hmbSchedulePickerOutputHandleRefresh(",
    "export function hmbPreparePickerSlotTransition(",
    "function applySlotView(",
    "function remapVideoCompanionSlots(",
    "export function deleteVideoSlotState(",
    "export function swapVideoSlotState(",
    "function hmbIsGeneratedDepthVideo(",
    "function hmbIsGeneratedMotionGuideVideo(",
    "function hmbExplicitCompanionSourceSlot(",
    "export function hmbReleaseGeneratedBundleIdentityForUserEdit(",
    "export function hmbClearGeneratedDepthPairIdentity(",
):
    if retired_fixed_slot_helper in picker_widget_text:
        raise AssertionError(
            "Picker Widget fixed-slot mutation helper remains: "
            f"{retired_fixed_slot_helper}"
        )
for retired_fixed_slot_control in (
    'id="slot-select"',
    'id="add-slot"',
    'id="clear-slot"',
    'id="delete-slot"',
    'id="move-slot-up"',
    'id="move-slot-down"',
):
    if retired_fixed_slot_control in picker_widget_text:
        raise AssertionError(
            "Picker Widget fixed-slot control remains: "
            f"{retired_fixed_slot_control}"
        )
for forbidden_slot_gate in (
    "@video1 is reserved for Color Playblast",
    "Remove generated Depth/Motion Guide companions before",
    "playblastBindingReady",
    "PLAYBLAST requires a completed READ snapshot, at least one Color Pick binding",
    "&& bindingReady",
):
    if forbidden_slot_gate in picker_widget_text:
        raise AssertionError(f"Picker user slot restriction remains: {forbidden_slot_gate}")
for anchor in (
    "def _observed_state_slot_count(",
    "used_uids: set[str] = set()",
    "if not uid or uid in used_uids:",
    'uid = f"video-{digest}-{collision_index}"',
    'item["video_uid"] = uid',
    'item["source_uid"] = uid',
    'item["legacy_video_slot"] = legacy_slot',
    "Retained {len(selected)} catalog videos but limited the active ",
    'project_video_path = _clean(item.get("project_video_path"))',
):
    if anchor not in picker_text:
        raise AssertionError(f"Picker no-loss catalog migration anchor missing: {anchor}")
for anchor in (
    "Typed auxiliary catalog behavior (English)",
    "타입 기반 보조 영상 카탈로그 동작 (한글)",
    "New Picker generation appends successful checked outputs",
    "Original, Mask, Depth, Motion Guide order",
    "catalog can retain more than ten assets",
    "at most ten may be selected",
    "Selected cards are read left-to-right and then top-to-bottom",
    "stable video UIDs",
    "grants no creative priority or authority",
    "Downstream connections and manual Prompt video rows remain independently usable",
    "`PICKER_OUT` publishes metadata for the current ordered selection",
    "`VIDEO_OUT` publishes the same paths as one `list[str]` generator connection",
    "there are no per-video output ports",
    "Depth is an optional typed catalog asset",
    "transient @videoN position",
    "no existing catalog asset is overwritten",
):
    if anchor not in guide_text:
        raise AssertionError(f"Guide typed auxiliary slot anchor missing: {anchor}")
for anchor in (
    "Persistent generated catalog",
    "<scene>_playblast_<unique-token>.mp4",
    "<scene>_depth_playblast_<unique-token>.mp4",
    "<scene>_motion_guide_<unique-token>.mp4",
    "unique immutable MP4/sidecar pair is appended to the catalog",
    "does not delete the underlying generated or imported MP4",
    "VIDEO_OUT may be connected directly to a generator's single ordered video-list input",
    "The two values are built from the same immutable selection snapshot",
    "PICKER_OUT schema v5 publishes only the selected catalog records",
    "visible row-major drag order",
    "at most ten",
):
    if anchor not in guide_text:
        raise AssertionError(
            f"Guide append-only catalog/output anchor missing: {anchor}"
        )
for anchor in (
    "256 shared grayscale `surfaceShader`/shading-group buckets",
    "Depth v7 preserves an authored, resolvable cutout-alpha signal",
    "ambiguous or unresolvable required cutout fails closed",
    "`alpha_cutout_smooth_preserved_count`",
    "nested `cutout_transparency` audit",
    "every visible polygon-mesh or NURBS-surface full DAG instance path",
    "median of the positive active-camera-space depths",
    "every full DAG shape path on every rendered output frame",
    "`normalized_power`, `contrast_exponent=1.0`",
    "1st and 99th percentiles of screen-valid Actor-marker representative depths",
    "up to 128 API mesh vertices and 64 polygon centers",
    "disjoint normalization accounting",
):
    if anchor not in guide_text:
        raise AssertionError(f"Guide v7 Depth contract anchor missing: {anchor}")
for anchor in (
    "Motion Guide v5 uses a compact core-control skeleton",
    "`hmb_target_neutral_motion_guide_v5`",
    "The immediately preceding v4 identifier is retained only for cleanup and diagnostics",
    "v2 and v3 remain fully retired",
    "weighted skinCluster influences",
    "Object/background markers remain rigid-transform targets",
    "Core body joints remain a motion-intent guide through self-occlusion",
    "schema version 2",
    "final evaluated Blend Shape weight",
    "raw-value provenance",
    "Raw NURBS controller-curve geometry is never rendered",
    "front-facing",
    "first visible hit",
    "Unknown Blend Shape aliases",
    "target-delta heatmaps",
    "render_scope_nonintermediate_deformed_visible_semantic_mesh_edges",
    "Alpha-driven cards are explicitly excluded",
    "face_semantic_surface_audit",
    "jaw center remains missing",
    "Frame-local DAG visibility caching",
):
    if anchor not in guide_text:
        raise AssertionError(f"Guide v5 Motion contract anchor missing: {anchor}")
if "samplerInfo" in guide_text:
    raise AssertionError("Guide must not describe the retired samplerInfo Depth path.")
for retired_public_output_claim in tuple(
    f"VIDEO{slot}_OUT" for slot in range(1, 11)
):
    if retired_public_output_claim in guide_text or retired_public_output_claim in readme_text:
        raise AssertionError(
            "Retired public per-video output remains in current guidance: "
            f"{retired_public_output_claim}"
        )
for anchor in (
    'DEPTH_PLAYBLAST_PROFILE = "hmb_camera_space_depth_v7"',
    'MOTION_GUIDE_PROFILE = "hmb_target_neutral_motion_guide_v5"',
    "MOTION_GUIDE_SCHEMA_VERSION = 2",
    '"schema_version": MOTION_GUIDE_SCHEMA_VERSION',
    "MOTION_GUIDE_FACE_BROW_RGB = (176, 96, 255)",
    "MOTION_GUIDE_FACE_EYE_RGB = (48, 196, 255)",
    "MOTION_GUIDE_FACE_MOUTH_RGB = (255, 72, 180)",
    "MOTION_GUIDE_FACE_JAW_RGB = (255, 176, 64)",
    '"schema": "hmb-maya-depth-playblast"',
    '"schema": MOTION_GUIDE_SCHEMA',
    '"direction": "near_white_far_black"',
    '"temporal_normalization": "fixed_for_complete_sequence"',
    '"encoding_curve": "normalized_power"',
    '"proxy_preview_recovery"',
    '"assignment_verification"',
    '"object_bbox_camera_depth"',
    '"color_picker_style_shared_gray_material_buckets"',
    '"per_shape_path_per_output_frame"',
    '"median_positive_camera_depth_of_world_bbox_corners"',
    '"screen_valid_foreground_percentile_bounds"',
    "DEPTH_NEAR_COLOR = 0.9",
    "DEPTH_CAMERA_NEAR_SAFETY_MARGIN = 0.1",
    '"grayscale_bucket_count"',
    "DEPTH_CONTRAST_EXPONENT = 1.0",
    "DEPTH_SCREEN_VERTEX_SAMPLE_LIMIT = 128",
    "DEPTH_SCREEN_POLYGON_CENTER_SAMPLE_LIMIT = 64",
    'DEPTH_REJECTION_ACCOUNTING_POLICY = "disjoint_normalization_outcomes"',
    'CUTOUT_TRANSPARENCY_POLICY = "preserve_authored_material_out_transparency_v1"',
    "def _material_cutout_evidence(",
    "def _ensure_authored_cutout_snapshot(",
    "def _assign_marker_group_preserving_cutouts(",
    "def _depth_cutout_surface_group(",
    '"alpha_cutout_smooth_preserved_count"',
    '"cutout_transparency"',
    '"rejection_accounting_policy": DEPTH_REJECTION_ACCOUNTING_POLICY',
    "def _depth_screen_sample_evidence(",
    '"screen_valid_foreground_percentile_bounds"',
    '"hardwareRenderingGlobals.renderDepthOfField"',
    '"hardwareRenderingGlobals.hwFogEnable"',
    'outputTarget="renderer"',
    "fresh=True",
    'getattr(dag_path, "isTemplated", None)',
    "def _potentially_visible_unsupported_depth_drawables(",
    "def _render_motion_guide_pass(",
    '"target_neutral_core_motion_plus_visible_face_semantic_rgb"',
    '"maya_skin_influence_transform_blendshape_and_curve_driver_evaluation"',
    '"final_evaluated_blendshape_weight_raw_value"',
    '"connected_numeric_nurbs_curve_controller_plug_raw_value_provenance_only"',
    '"surface_pinned_brow_eyelid_mouth_jaw_landmarks_only;"',
    '"raw_nurbs_curve_geometry_never_rendered"',
    '"front_facing_vertex_normal_plus_camera_ray_first_hit_visible_only"',
    '"semantic_bilateral_jaw_midpoint_surface_inference"',
    '"semantic_face_axis_center_surface_fallback"',
    '"semantic_bilateral_jaw_surface_profile_inference"',
    '"target_scope_semantic_curve_control_keyed_numeric_plugs_only"',
    '"render_scope_nonintermediate_deformed_visible_semantic_mesh_edges"',
    '"render_scope_semantic_mesh_vertex"',
    '"alpha_driven_card_excluded"',
    '"face_semantic_surface_audit"',
    '"keyed_semantic_driver_audit"',
    '"jaw_center_candidate_evidence"',
    '"surface_distance_then_vertex_index"',
    '"raw_alias_and_value_preserved_sidecar_only_no_raster_guess"',
    '"curve_geometry_rendered": False',
    '"appearance_authority": "zero"',
    '"motion_authority": "derived_decoder_of_video1_only"',
):
    if anchor not in maya_runner_text:
        raise AssertionError(f"Maya paired-Depth contract anchor missing: {anchor}")
if "samplerInfo" in maya_runner_text:
    raise AssertionError(
        "Maya v5 Depth must use Color Picker material buckets, not samplerInfo."
    )

for relative in PYTHON_COMPILE_TARGETS:
    source = (ROOT / relative).read_text(encoding="utf-8")
    compile(source, relative, "exec")

# Maya 2026 embeds Python 3.11.  The Griptape host runs on Python 3.12, but
# the isolated mayabatch runner must remain valid under Maya's own grammar.
ast.parse(
    maya_runner_text,
    filename="resources/maya/HMB_Maya_Background_Preview.py",
    feature_version=(3, 11),
)

common_spec = importlib.util.spec_from_file_location(
    "_hmb_release_policy_verifier",
    ROOT / "_hmb_common.py",
)
if common_spec is None or common_spec.loader is None:
    raise AssertionError("Unable to load the Agent policy verifier.")
common_module = importlib.util.module_from_spec(common_spec)
common_spec.loader.exec_module(common_module)
if common_module._AGENT_POLICY_VERSION != POLICY_VERSION:
    raise AssertionError("Runtime Agent policy version constant mismatch.")
if common_module._AGENT_POLICY_CONTRACT_SHA256 != CONTRACT_SHA256:
    raise AssertionError("Runtime Agent contract digest constant mismatch.")
if common_module.AGENT_RULE_DATA_PATH_ENV != AGENT_POLICY_PATH_ENV:
    raise AssertionError("Runtime external Agent policy environment name mismatch.")
if common_module.AGENT_RULE_DATA_PATH is not None:
    raise AssertionError("Runtime must not retain a bundled Agent policy fallback path.")

bundled_policy_path = ROOT / "resources" / "agent" / "hmb_agent_core.dat"
if bundled_policy_path.exists():
    raise AssertionError("Agent policy must not be bundled in the public source tree.")

external_policy_report = {
    "bundled": False,
    "path_env": AGENT_POLICY_PATH_ENV,
    "envelope_schema": common_module._AGENT_POLICY_ENVELOPE_SCHEMA,
    "signature_algorithm": common_module._AGENT_POLICY_SIGNATURE_ALGORITHM,
    "signing_key_id": common_module._AGENT_POLICY_SIGNING_KEY_ID,
    "maximum_envelope_bytes": common_module._AGENT_POLICY_MAX_ENVELOPE_BYTES,
    "maximum_decompressed_bytes": common_module._AGENT_POLICY_MAX_DECOMPRESSED_BYTES,
}
sealed_policy_fragments: tuple[bytes, ...] = ()
external_policy_path_text = str(os.environ.get(AGENT_POLICY_PATH_ENV, "")).strip()
require_external_policy = str(
    os.environ.get(REQUIRE_EXTERNAL_POLICY_ENV, "")
).strip().casefold() in {"1", "true", "yes", "on"}
if external_policy_path_text:
    try:
        agent_data = common_module._read_agent_policy_envelope(
            Path(external_policy_path_text)
        )
    except Exception:
        raise AssertionError(
            "Configured external Agent policy could not be read."
        ) from None
    sealed_payload = common_module._decode_signed_agent_policy_envelope(agent_data)
    common_module._validate_agent_policy_payload(sealed_payload)
    if sealed_payload.get("schema") != common_module._AGENT_POLICY_SCHEMA:
        raise AssertionError("Unexpected signed Agent payload schema.")
    if sealed_payload.get("final_policy_version") != POLICY_VERSION:
        raise AssertionError("Signed Agent policy version mismatch.")
    if sealed_payload.get("final_motion_look_policy_sha256") != CONTRACT_SHA256:
        raise AssertionError("Signed Agent contract digest mismatch.")
    for field in ("policy", "binding"):
        rules = str(sealed_payload[field])
        if digest(rules.encode("utf-8")) != sealed_payload[f"{field}_sha256"]:
            raise AssertionError(f"Signed Agent {field} digest mismatch.")
        if not rules.strip():
            raise AssertionError(f"Sealed Agent {field} is empty.")
        normalized_rules = rules.casefold()
        for anchor in (
            "final creative authority",
            "interpretation hint",
            "never downgrade supplied content to context-only",
            "explicit user goal may use any visible property",
        ):
            if anchor not in normalized_rules:
                raise AssertionError(
                    f"Sealed Agent goal-final-authority anchor missing: {anchor}"
                )
        for forbidden in (
            "a missing role falls back to context-only use",
            "a missing local binding prevents local control authority",
            "zero identity or final-look authority",
        ):
            if forbidden in normalized_rules:
                raise AssertionError(
                    f"Sealed Agent connection restriction remains: {forbidden}"
                )
    sealed_policy_fragments = tuple(
        str(item).encode("utf-8")
        for item in (
            *sealed_payload.get("final_motion_look_policy_clauses", ()),
            *sealed_payload.get("video_appearance_isolation_clauses", ()),
        )
        if str(item)
    )
    if not sealed_policy_fragments:
        raise AssertionError("Signed Agent policy contract is incomplete.")
elif require_external_policy:
    raise AssertionError(
        f"{AGENT_POLICY_PATH_ENV} is required for this internal release audit."
    )

for relative in ALLOWLIST:
    source_bytes = (ROOT / relative).read_bytes()
    if any(fragment in source_bytes for fragment in sealed_policy_fragments):
        raise AssertionError(f"Plaintext Agent policy exposed in release source: {relative}")

for relative in ALLOWLIST:
    lowered = relative.casefold()
    if (
        lowered.endswith("hmb_agent_core.dat")
        or Path(relative).suffix.casefold() in {".env", ".jwk", ".key", ".p12", ".pem", ".pfx"}
    ):
        raise AssertionError(f"Sensitive file type entered the release allowlist: {relative}")

source_hashes = {
    relative: digest((ROOT / relative).read_bytes()) for relative in ALLOWLIST
}

release_slug = RELEASE_VERSION.replace(".", "_")
stage_root = Path(tempfile.mkdtemp(prefix=f"hmb_release_{release_slug}_"))
atexit.register(shutil.rmtree, stage_root, ignore_errors=True)
for top_name, _archive_path in ARCHIVES:
    for relative in ALLOWLIST:
        destination = stage_root / top_name / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
        if digest(destination.read_bytes()) != source_hashes[relative]:
            raise AssertionError(f"Staging hash mismatch: {top_name}/{relative}")

DIST.mkdir(parents=True, exist_ok=True)
archive_relative_maps: list[dict[str, str]] = []
archive_reports = []
extraction_root = Path(tempfile.mkdtemp(prefix=f"hmb_verify_{release_slug}_"))
atexit.register(shutil.rmtree, extraction_root, ignore_errors=True)
for top_name, archive_path in ARCHIVES:
    temporary_archive = archive_path.with_name(
        f".{archive_path.name}.{uuid.uuid4().hex}.tmp"
    )
    with zipfile.ZipFile(
        temporary_archive,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for relative in ALLOWLIST:
            member_name = f"{top_name}/{relative}"
            member = zipfile.ZipInfo(member_name, REPRODUCIBLE_ZIP_DATE_TIME)
            member.compress_type = zipfile.ZIP_DEFLATED
            member.create_system = 3
            member.external_attr = REPRODUCIBLE_ZIP_MODE << 16
            archive.writestr(
                member,
                (stage_root / top_name / Path(relative)).read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )

    with zipfile.ZipFile(temporary_archive, "r") as archive:
        if archive.testzip() is not None:
            raise AssertionError(f"Corrupt archive member: {archive.testzip()}")
        infos = archive.infolist()
        if len(infos) != len(ALLOWLIST) or any(info.is_dir() for info in infos):
            raise AssertionError(
                f"{archive_path.name} must contain {len(ALLOWLIST)} files and no directories."
            )
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise AssertionError(f"Duplicate archive member in {archive_path.name}.")
        expected_names = [f"{top_name}/{relative}" for relative in ALLOWLIST]
        if names != expected_names:
            raise AssertionError(f"Archive allowlist/order mismatch: {archive_path.name}")
        if any(info.date_time != REPRODUCIBLE_ZIP_DATE_TIME for info in infos):
            raise AssertionError(f"Archive timestamp is not reproducible: {archive_path.name}")
        if any((info.external_attr >> 16) != REPRODUCIBLE_ZIP_MODE for info in infos):
            raise AssertionError(f"Archive permission is not reproducible: {archive_path.name}")
        relative_map = {}
        for info in infos:
            member_path = PurePosixPath(info.filename)
            if member_path.parts[0] != top_name or len(member_path.parts) < 2:
                raise AssertionError(f"Unexpected archive root: {info.filename}")
            relative = PurePosixPath(*member_path.parts[1:]).as_posix()
            assert_safe_relative(relative)
            member_hash = digest(archive.read(info))
            if source_hashes.get(relative) != member_hash:
                raise AssertionError(f"Archive/source hash mismatch: {info.filename}")
            relative_map[relative] = member_hash
        archive_relative_maps.append(relative_map)

    os.replace(temporary_archive, archive_path)
    extraction_target = extraction_root / top_name
    extraction_target.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive_path, "r") as archive:
        archive.extractall(extraction_target)
    extracted_library = extraction_target / top_name
    extracted_files = sorted(
        path.relative_to(extracted_library).as_posix()
        for path in extracted_library.rglob("*")
        if path.is_file()
    )
    if extracted_files != sorted(ALLOWLIST):
        raise AssertionError(
            f"Independent extraction allowlist mismatch: {archive_path.name}"
        )
    for relative in ALLOWLIST:
        extracted = extracted_library / Path(relative)
        if digest(extracted.read_bytes()) != source_hashes[relative]:
            raise AssertionError(
                f"Independent extraction hash mismatch: "
                f"{archive_path.name}/{relative}"
            )
    archive_reports.append(
        {
            "path": str(archive_path),
            "bytes": archive_path.stat().st_size,
            "sha256": digest(archive_path.read_bytes()),
            "verified_extraction": str(extracted_library),
        }
    )

release_manifest = {
    "schema": "hmb-release-manifest-v1",
    "release_version": RELEASE_VERSION,
    "policy_version": POLICY_VERSION,
    "contract_sha256": CONTRACT_SHA256,
    "external_agent_policy": external_policy_report,
    "reproducible_zip": {
        "member_timestamp": "2020-01-01T00:00:00Z",
        "member_mode": "100644",
        "compression": "deflate-9",
    },
    "source_files": [
        {
            "path": relative,
            "bytes": (ROOT / relative).stat().st_size,
            "sha256": source_hashes[relative],
        }
        for relative in ALLOWLIST
    ],
    "archives": [
        {
            "name": Path(report["path"]).name,
            "bytes": report["bytes"],
            "sha256": report["sha256"],
        }
        for report in archive_reports
    ],
}
manifest_text = json.dumps(
    release_manifest,
    ensure_ascii=False,
    sort_keys=True,
    indent=2,
) + "\n"
write_text_atomic(RELEASE_MANIFEST_PATH, manifest_text)
checksum_targets = [
    *(Path(report["path"]) for report in archive_reports),
    RELEASE_MANIFEST_PATH,
]
checksum_text = "".join(
    f"{digest(path.read_bytes())}  {path.name}\n" for path in checksum_targets
)
write_text_atomic(RELEASE_CHECKSUMS_PATH, checksum_text)
for line in RELEASE_CHECKSUMS_PATH.read_text(encoding="utf-8").splitlines():
    expected_hash, filename = line.split("  ", 1)
    target = DIST / filename
    if not target.is_file() or digest(target.read_bytes()) != expected_hash:
        raise AssertionError(f"Release checksum verification failed: {filename}")

print(
    json.dumps(
        {
            "release_version": RELEASE_VERSION,
            "policy_version": POLICY_VERSION,
            "contract_sha256": CONTRACT_SHA256,
            "file_count": len(ALLOWLIST),
            "stage_root": str(stage_root),
            "extraction_root": str(extraction_root),
            "archives": archive_reports,
            "release_manifest": str(RELEASE_MANIFEST_PATH),
            "checksums": str(RELEASE_CHECKSUMS_PATH),
        },
        ensure_ascii=False,
        indent=2,
    )
)
