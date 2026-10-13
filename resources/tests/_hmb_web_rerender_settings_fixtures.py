"""Synthetic parent-request fixtures; no live records or credentials."""
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _hmb_web_rerender as web


def wire_settings(settings=None):
    if settings is None:
        return {"model": "doubao-seedance-2-5-260628", "input_mode": "Multimodal References",
                "quality": "720p", "resolution": "720p", "aspect_ratio": "16:9",
                "duration_seconds": 4, "generate_audio": False, "priority": 0,
                "omni_reference_task_type": "reference"}
    aliases = {"model_id": "model", "resolution": "quality", "ratio": "aspect_ratio", "duration": "duration_seconds"}
    result = {aliases.get(key, key): deepcopy(value) for key, value in settings.items()
              if key not in {"task", "seed", "camera_fixed"}}
    task = settings.get("task")
    if settings["model_id"] == "doubao-seedance-2-5-260628" and task in {
        "Reference to Video", "Video Editing", "Video Extension"
    }:
        result["omni_reference_task_type"] = {"Reference to Video": "reference", "Video Editing": "edit", "Video Extension": "extend"}[task]
    return result


def freeze_command(command, settings=None):
    command = deepcopy(command)
    command["frozen_generation_settings_schema"] = web.PARENT_SETTINGS_SCHEMA
    command["frozen_generation_settings"] = deepcopy(settings if settings is not None else wire_settings())
    digest = web._digest(command["frozen_generation_settings"])
    command["frozen_generation_settings_sha256"] = digest
    command["frozen_generation_settings_binding_sha256"] = web._digest({
        "schema": web.PARENT_SETTINGS_SCHEMA, "parent_task_id": command["parent_task_id"],
        "project_id": command["project_id"], "project_name": command["project_name"],
        "frozen_generation_settings_sha256": digest,
    })
    return command
