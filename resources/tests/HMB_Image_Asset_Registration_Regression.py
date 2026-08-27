from __future__ import annotations

from copy import deepcopy
import base64
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]


def load_module():
    path = ROOT / "HMBImageAssetLibrary.py"
    spec = importlib.util.spec_from_file_location(
        "hmb_image_asset_registration_regression",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


asset_library = load_module()
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="
)

tmp_parent = ROOT / ".tmp"
tmp_parent.mkdir(parents=True, exist_ok=True)
test_root = Path(tempfile.mkdtemp(prefix="hmb_asset_registration_", dir=tmp_parent))
try:
    catalog_root = test_root / "Projects"
    project_root = catalog_root / "shot_registration"
    existing_path = project_root / "Environment" / "Background" / "existing.png"
    candidate_path = (
        project_root
        / "Character Appearance"
        / "Full body - full appearance"
        / "candidate.png"
    )
    existing_path.parent.mkdir(parents=True)
    candidate_path.parent.mkdir(parents=True)
    existing_path.write_bytes(PNG_1X1)
    candidate_path.write_bytes(PNG_1X1)
    legacy_manifest_path = project_root / "hmb_image_assets.json"
    manifest_path = project_root / ".json" / "hmb_image_assets.json"
    legacy_manifest_path.write_text(
        json.dumps(
            {
                "schema": "legacy-project-metadata",
                "note": "preserve top-level metadata",
                "assets": [
                    {
                        "path": existing_path.relative_to(project_root).as_posix(),
                        "asset_id": "ExistingBackground",
                        "image_name": "Existing Background",
                        "source_type": "Environment / Background",
                        "scope": "Main background",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = asset_library._load_project_catalog(
        catalog_root,
        asset_library._default_state(),
    )
    state = asset_library._select_catalog_project(state, project_root)
    existing = next(
        item for item in state["assets"] if item["image_name"] == "Existing Background"
    )
    candidate = next(
        item for item in state["assets"] if item["relative_path"].endswith("candidate.png")
    )
    assert existing["registered"] is True
    assert candidate["registered"] is False
    assert state["status"]["registered_asset_count"] == 1
    assert state["status"]["unregistered_asset_count"] == 1

    # A forged frontend flag cannot grant project authority without membership
    # in the server-read manifest.
    forged = deepcopy(state)
    forged_candidate = next(
        item for item in forged["assets"] if item["asset_library_id"] == candidate["asset_library_id"]
    )
    forged_candidate["registered"] = True
    forged_candidate["selected"] = True
    forged_candidate["selection_order"] = 1
    forged_output = asset_library._build_output_payload(forged)
    assert forged_output["ordered_images"] == []
    assert forged_output["verified_assets"] == []
    assert forged_output["imported_images"] == []
    assert asset_library._selected_media_values(forged, {}) == []

    request = {
        "request_id": "register-candidate-1",
        "project_uid": state["project_uid"],
        "asset_library_id": candidate["asset_library_id"],
        "relative_path": candidate["relative_path"],
        "image_name": "Hero Final",
        "asset_id": "HeroRig",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "custom_source_type": "",
    }
    registered_state = asset_library._apply_asset_registration(state, request)
    assert manifest_path.is_file()
    assert not legacy_manifest_path.exists()
    assert (
        project_root / ".json" / asset_library.ASSET_MANIFEST_LOCK_NAME
    ).is_file()
    assert not (project_root / asset_library.ASSET_MANIFEST_LOCK_NAME).exists()
    registered_candidate = next(
        item
        for item in registered_state["assets"]
        if item["asset_library_id"] == candidate["asset_library_id"]
    )
    assert registered_candidate["registered"] is True
    assert registered_candidate["image_name"] == "Hero Final"
    assert registered_candidate["asset_id"] == "HeroRig"
    assert registered_candidate["image_main_type"] == "Character"
    assert registered_candidate["image_sub_type"] == "Full Appearance"
    assert registered_candidate["source_type"] == "Character Appearance"
    assert registered_candidate["scope_candidate"] == "Full body / full appearance"
    assert registered_state["project_cache_uid"] == state["project_cache_uid"]
    assert registered_candidate["media_signature"] == asset_library._asset_file_facts(
        candidate_path,
        project_uid=registered_state["project_cache_uid"],
        relative_path=candidate["relative_path"],
    )[3]
    assert registered_state["asset_registration_request"] == {}
    assert registered_state["asset_registration_result"] == {
        "request_id": "register-candidate-1",
        "ok": True,
        "asset_library_id": candidate["asset_library_id"],
        "message": "Registered in hmb_image_assets.json.",
    }

    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert document["schema"] == "legacy-project-metadata"
    assert document["note"] == "preserve top-level metadata"
    assert document["project_cache_uid"] == state["project_cache_uid"]
    assert len(document["assets"]) == 2
    persisted = next(
        item for item in document["assets"] if item.get("asset_id") == "HeroRig"
    )
    assert persisted == {
        "path": candidate_path.relative_to(project_root).as_posix(),
        "asset_id": "HeroRig",
        "image_name": "Hero Final",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "source_type": "Character Appearance",
        "custom_source_type": "",
        "scope": "Full body / full appearance",
    }
    assert not list((project_root / ".json").glob(".hmb_image_assets.json.*.tmp"))

    selected_state = deepcopy(registered_state)
    selected_candidate = next(
        item
        for item in selected_state["assets"]
        if item["asset_library_id"] == candidate["asset_library_id"]
    )
    selected_candidate["selected"] = True
    selected_candidate["selection_order"] = 1
    selected_output = asset_library._build_output_payload(selected_state)
    assert [item["asset_id"] for item in selected_output["verified_assets"]] == [
        "HeroRig"
    ]
    assert selected_output["imported_images"] == []
    assert asset_library._selected_media_values(selected_state, {}) == [
        str(candidate_path.resolve()).replace("\\", "/")
    ]

    # IMAGE_IMPORT_IN sources use the same passport and copy directly into one
    # chosen existing asset folder before the manifest record is created.
    external_source = test_root / "external_source.png"
    external_source.write_bytes(PNG_1X1)
    imported_state, media_by_uid = asset_library._merge_import_input(
        registered_state,
        [str(external_source)],
    )
    imported_asset = next(
        item for item in imported_state["assets"] if item["source_kind"] == "user"
    )
    assert imported_asset["selected"] is True
    import_request = {
        "request_id": "register-import-1",
        "project_uid": imported_state["project_uid"],
        "asset_library_id": imported_asset["asset_library_id"],
        "source_kind": "user",
        "source_uid": imported_asset["source_uid"],
        "relative_path": "",
        "target_folder": "Environment/Background",
        "image_name": "Imported Forest Final",
        "asset_id": "ImportedForestFinal",
        "image_main_type": "Environment / Background",
        "image_sub_type": "Main Background",
        "custom_source_type": "",
    }
    manifest_before_root_rejection = manifest_path.read_bytes()
    for rejected_folder in ("", "$root"):
        rejected_request = dict(import_request)
        rejected_request["request_id"] = f"reject-root-{rejected_folder or 'blank'}"
        rejected_request["target_folder"] = rejected_folder
        try:
            asset_library._apply_asset_registration(
                imported_state,
                rejected_request,
                media_by_uid,
            )
        except ValueError as exc:
            assert "Folder" in str(exc)
        else:
            raise AssertionError("External Add must reject the project root.")
        assert not (project_root / "external_source.png").exists()
        assert manifest_path.read_bytes() == manifest_before_root_rejection

    imported_registered = asset_library._apply_asset_registration(
        imported_state,
        import_request,
        media_by_uid,
    )
    copied_path = (
        project_root
        / "Environment"
        / "Background"
        / "external_source.png"
    )
    assert copied_path.read_bytes() == PNG_1X1
    assert not (
        project_root / "Environment" / "Background" / "ImportedForestFinal"
    ).exists(), "Add must not create an Asset ID directory."
    collision_copy = asset_library._copy_import_to_project(
        imported_asset,
        str(external_source),
        project_root,
        "Environment/Background",
    )
    assert collision_copy.name == "external_source_2.png"
    collision_copy.unlink()
    assert not any(
        item["source_kind"] == "user" and item["source_uid"] == imported_asset["source_uid"]
        for item in imported_registered["assets"]
    )
    copied_asset = next(
        item
        for item in imported_registered["assets"]
        if item["relative_path"]
        == "Environment/Background/external_source.png"
    )
    assert copied_asset["registered"] is True
    assert copied_asset["selected"] is True
    assert copied_asset["selection_order"] == 1
    assert copied_asset["import_source_uid"] == imported_asset["source_uid"]
    merged_again, _media_again = asset_library._merge_import_input(
        imported_registered,
        [str(external_source)],
    )
    assert not any(
        item["source_kind"] == "user" and item["source_uid"] == imported_asset["source_uid"]
        for item in merged_again["assets"]
    ), "A copied import must not return as a duplicate external card."
    persisted_import = next(
        item
        for item in json.loads(manifest_path.read_text(encoding="utf-8"))["assets"]
        if item.get("asset_id") == "ImportedForestFinal"
    )
    assert (
        persisted_import["path"]
        == "Environment/Background/external_source.png"
    )
    assert persisted_import["import_source_uid"] == imported_asset["source_uid"]

    # LoadImage publishes portable Griptape project macros such as {inputs}/...
    # rather than absolute paths. Registration must resolve that reference on
    # the server and still place the file directly in the selected asset folder.
    macro_source = test_root / "macro_character.png"
    macro_source.write_bytes(PNG_1X1)
    macro_input = SimpleNamespace(
        value="{inputs}/macro_character.png",
        name="macro_character.png",
    )
    macro_state, macro_media = asset_library._merge_import_input(
        imported_registered,
        [macro_input],
    )
    macro_asset = next(
        item for item in macro_state["assets"] if item["source_kind"] == "user"
    )
    macro_request = {
        "request_id": "register-macro-import",
        "project_uid": macro_state["project_uid"],
        "asset_library_id": macro_asset["asset_library_id"],
        "source_kind": "user",
        "source_uid": macro_asset["source_uid"],
        "relative_path": "",
        "target_folder": "Character Appearance/Full body - full appearance",
        "image_name": "Macro Character",
        "asset_id": "MacroCharacter",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "custom_source_type": "",
    }
    original_resolver = asset_library._resolve_import_file_reference
    asset_library._resolve_import_file_reference = (
        lambda value: macro_source.resolve()
        if value == "{inputs}/macro_character.png"
        else original_resolver(value)
    )
    try:
        macro_registered = asset_library._apply_asset_registration(
            macro_state,
            macro_request,
            macro_media,
        )
    finally:
        asset_library._resolve_import_file_reference = original_resolver
    macro_copy = (
        project_root
        / "Character Appearance"
        / "Full body - full appearance"
        / "macro_character.png"
    )
    assert macro_copy.read_bytes() == PNG_1X1
    assert any(
        item["registered"] and item["asset_id"] == "MacroCharacter"
        for item in macro_registered["assets"]
    )

    embedded_input = SimpleNamespace(
        value=PNG_1X1,
        name="generated_frame.png",
    )
    embedded_state, embedded_media = asset_library._merge_import_input(
        macro_registered,
        [embedded_input],
    )
    embedded_asset = next(
        item for item in embedded_state["assets"] if item["source_kind"] == "user"
    )
    embedded_request = {
        "request_id": "register-embedded-import",
        "project_uid": embedded_state["project_uid"],
        "asset_library_id": embedded_asset["asset_library_id"],
        "source_kind": "user",
        "source_uid": embedded_asset["source_uid"],
        "relative_path": "",
        "target_folder": "Character Appearance/Full body - full appearance",
        "image_name": "Generated Hero Frame",
        "asset_id": "GeneratedHeroFrame",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "custom_source_type": "",
    }
    embedded_registered = asset_library._apply_asset_registration(
        embedded_state,
        embedded_request,
        embedded_media,
    )
    embedded_copy = (
        project_root
        / "Character Appearance"
        / "Full body - full appearance"
        / "generated_frame.png"
    )
    assert embedded_copy.read_bytes() == PNG_1X1
    assert any(
        item["registered"] and item["asset_id"] == "GeneratedHeroFrame"
        for item in embedded_registered["assets"]
    )

    # A freshly imported image starts unclassified. The backend can preserve an
    # explicit unclassified record for compatibility, while the UI requires the
    # new Main/Sub pair before a user can submit registration.
    optional_role_source = test_root / "optional_role_source.png"
    optional_role_source.write_bytes(PNG_1X1)
    optional_state, optional_media = asset_library._merge_import_input(
        embedded_registered,
        [str(optional_role_source)],
    )
    optional_asset = next(
        item for item in optional_state["assets"] if item["source_kind"] == "user"
    )
    assert optional_asset["image_main_type"] == "Select Image Main Type"
    assert optional_asset["image_sub_type"] == ""
    assert optional_asset["source_type"] == "Role Required / Select Source Type"
    optional_request = {
        "request_id": "register-without-creative-role",
        "project_uid": optional_state["project_uid"],
        "asset_library_id": optional_asset["asset_library_id"],
        "source_kind": "user",
        "source_uid": optional_asset["source_uid"],
        "relative_path": "",
        "target_folder": "Environment/Background",
        "image_name": "Unclassified User Idea",
        "asset_id": "UnclassifiedUserIdea",
        "image_main_type": "",
        "image_sub_type": "",
        "custom_source_type": "",
    }
    optional_registered = asset_library._apply_asset_registration(
        optional_state,
        optional_request,
        optional_media,
    )
    optional_copy = (
        project_root
        / "Environment"
        / "Background"
        / "optional_role_source.png"
    )
    assert optional_copy.read_bytes() == PNG_1X1
    optional_project_asset = next(
        item
        for item in optional_registered["assets"]
        if item["asset_id"] == "UnclassifiedUserIdea"
    )
    assert optional_project_asset["registered"] is True
    assert optional_project_asset["image_main_type"] == "Select Image Main Type"
    assert optional_project_asset["image_sub_type"] == ""
    assert optional_project_asset["source_type"] == "Role Required / Select Source Type"
    assert optional_project_asset["custom_source_type"] == ""
    assert optional_project_asset["scope_candidate"] == ""

    # A manifest failure removes only the copied file and keeps the user's
    # existing selected asset folder intact.
    rollback_source = test_root / "rollback_source.png"
    rollback_source.write_bytes(PNG_1X1)
    rollback_state, rollback_media = asset_library._merge_import_input(
        optional_registered,
        [str(rollback_source)],
    )
    rollback_asset = next(
        item for item in rollback_state["assets"] if item["source_kind"] == "user"
    )
    rollback_request = {
        "request_id": "rollback-manifest-failure",
        "project_uid": rollback_state["project_uid"],
        "asset_library_id": rollback_asset["asset_library_id"],
        "source_kind": "user",
        "source_uid": rollback_asset["source_uid"],
        "relative_path": "",
        "target_folder": "Environment/Background",
        "image_name": "Rollback Asset",
        "asset_id": "RollbackAsset",
        "image_main_type": "Environment / Background",
        "image_sub_type": "Main Background",
        "custom_source_type": "",
    }
    original_manifest_writer = asset_library._write_asset_manifest_record

    def fail_manifest_write(*_args, **_kwargs):
        raise RuntimeError("simulated manifest write failure")

    asset_library._write_asset_manifest_record = fail_manifest_write
    try:
        try:
            asset_library._apply_asset_registration(
                rollback_state,
                rollback_request,
                rollback_media,
            )
        except RuntimeError as exc:
            assert "simulated manifest write failure" in str(exc)
        else:
            raise AssertionError("A manifest failure must reject the registration.")
    finally:
        asset_library._write_asset_manifest_record = original_manifest_writer
    assert not (
        project_root / "Environment" / "Background" / "rollback_source.png"
    ).exists()
    assert (project_root / "Environment" / "Background").is_dir()

    corrupt_source = test_root / "corrupt_source.png"
    corrupt_source.write_bytes(b"this-is-not-a-decodable-image")
    corrupt_state, corrupt_media = asset_library._merge_import_input(
        optional_registered,
        [str(corrupt_source)],
    )
    corrupt_asset = next(
        item for item in corrupt_state["assets"] if item["source_kind"] == "user"
    )
    corrupt_request = {
        "request_id": "reject-corrupt-image",
        "project_uid": corrupt_state["project_uid"],
        "asset_library_id": corrupt_asset["asset_library_id"],
        "source_kind": "user",
        "source_uid": corrupt_asset["source_uid"],
        "relative_path": "",
        "target_folder": "Environment/Background",
        "image_name": "Corrupt Image",
        "asset_id": "CorruptImage",
        "image_main_type": "Custom / Context",
        "image_sub_type": "Context",
        "custom_source_type": "",
    }
    manifest_before_corrupt = manifest_path.read_bytes()
    try:
        asset_library._apply_asset_registration(
            corrupt_state,
            corrupt_request,
            corrupt_media,
        )
    except ValueError as exc:
        assert "could not be decoded" in str(exc)
    else:
        raise AssertionError("Corrupt image media must not be copied or registered.")
    assert manifest_path.read_bytes() == manifest_before_corrupt
    assert not (
        project_root
        / "Environment"
        / "Background"
        / "corrupt_source.png"
    ).exists()

    validation_path = project_root / "Validation" / "unregistered.png"
    validation_path.parent.mkdir(parents=True)
    validation_path.write_bytes(PNG_1X1)
    validation_relative = validation_path.relative_to(project_root).as_posix()
    validation_request = dict(request)
    validation_request.update(
        {
            "asset_library_id": asset_library._asset_library_id(
                registered_state["project_id"],
                validation_relative,
            ),
            "relative_path": validation_relative,
            "image_name": "Validation Candidate",
            "asset_id": "ValidationCandidate",
        }
    )

    manifest_before_invalid = manifest_path.read_bytes()
    invalid_scope = dict(validation_request)
    invalid_scope["request_id"] = "invalid-scope"
    invalid_scope["image_sub_type"] = "Main Background"
    try:
        asset_library._apply_asset_registration(registered_state, invalid_scope)
    except ValueError as exc:
        assert "valid Image Main Type and Sub Type pair" in str(exc)
    else:
        raise AssertionError("A Main/Sub Type mismatch must be rejected.")
    assert manifest_path.read_bytes() == manifest_before_invalid

    duplicate_id = dict(validation_request)
    duplicate_id["request_id"] = "duplicate-id"
    duplicate_id["asset_id"] = "ExistingBackground"
    try:
        asset_library._apply_asset_registration(registered_state, duplicate_id)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("A duplicate registered Asset ID must be rejected.")
    assert manifest_path.read_bytes() == manifest_before_invalid

    stale = dict(request)
    stale["request_id"] = "stale-project"
    stale["project_uid"] = "another-project"
    try:
        asset_library._apply_asset_registration(registered_state, stale)
    except ValueError as exc:
        assert "stale project" in str(exc)
    else:
        raise AssertionError("A stale project request must be rejected.")
    assert manifest_path.read_bytes() == manifest_before_invalid

    # Registration is create-only. Even a forged/stale Edit request cannot
    # change Image Name, Asset ID, Main Type, or Sub Type after Add succeeds.
    manifest_before_registered_edit = manifest_path.read_bytes()
    forbidden_registered_edit = dict(request)
    forbidden_registered_edit.update(
        {
            "request_id": "reject-registered-edit",
            "image_name": "Edited Hero",
            "asset_id": "EditedHero",
            "image_main_type": "Look Reference",
            "image_sub_type": "Color Mood",
        }
    )
    try:
        asset_library._apply_asset_registration(
            registered_state,
            forbidden_registered_edit,
        )
    except ValueError as exc:
        assert "already registered and cannot be edited" in str(exc)
    else:
        raise AssertionError("A registered asset must not expose an Edit operation.")
    assert manifest_path.read_bytes() == manifest_before_registered_edit

    # The writer repeats the same check while holding both manifest locks so a
    # concurrent Add cannot turn into an accidental update.
    forged_record = dict(persisted)
    forged_record.update(
        {
            "image_name": "Race Edited Hero",
            "asset_id": "RaceEditedHero",
        }
    )
    try:
        asset_library._write_asset_manifest_record(project_root, forged_record)
    except ValueError as exc:
        assert "already registered and cannot be edited" in str(exc)
    else:
        raise AssertionError("The locked manifest writer must reject existing paths.")
    assert manifest_path.read_bytes() == manifest_before_registered_edit
finally:
    shutil.rmtree(test_root, ignore_errors=True)

print("HMB image asset explicit registration and manifest authority regression: PASS")
