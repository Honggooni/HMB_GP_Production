from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_review as review


def main() -> None:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="hmb-review-regression-") as directory:
        base = Path(directory)
        media = base / "source.mp4"
        media.write_bytes(b"verified-source-identity")
        inputs = review.capture_inputs({"task": "Video Editing", "duration": 10,
            "video_references": [str(media), "https://private.invalid/video?token=SECRET"],
            "_hmb_generation_origin": {"shot_uuid": "shot-A", "name": "컷 01 · 점프 🎬"}, "broker_token": "SECRET"})
        local, remote = inputs["references"]
        assert local["content_sha256"] == hashlib.sha256(media.read_bytes()).hexdigest()
        assert local["content_status"] == "full_sha256"
        assert remote["content_status"] == "not_downloaded"
        assert "SECRET" not in json.dumps(inputs) and "private.invalid" not in json.dumps(inputs)
        checks += 4
        case_id = review.start_case("client-A", inputs, "exact submitted prompt", {"library_version": "0.7.82"},
                                    {"status": "succeeded", "coverage": [{"actual_pts": 0.5}]}, root=base)
        record = review.read_case("client-A", root=base)
        assert record and record["prompt_sha256"] == hashlib.sha256(b"exact submitted prompt").hexdigest()
        evidence = record["input_evidence_sha256"]
        assert review.start_case("client-A", {}, "changed current prompt", {}, {}, root=base) == case_id
        assert review.read_case("client-A", root=base)["submitted_prompt"] == "exact submitted prompt"
        assert review.read_case("client-A", root=base)["inputs"]["generation_origin"]["name"] == "컷 01 · 점프 🎬"
        checks += 3
        assert review.update_case("broker-A", case_id=case_id, status="running", root=base)
        assert review.read_case("broker-A", root=base)["inputs"] == inputs
        assert review.update_case("broker-B", case_id=case_id, status="running", root=base) is None
        assert review.update_case("historical-task", status="running", root=base) is None
        checks += 4
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda index: review.save_review("broker-A", score=2,
                category="motion", note=f"observed issue {index}", root=base), range(30)))
        reviewed = review.read_case("broker-A", root=base)
        assert len(reviewed["reviews"]) == 30
        assert reviewed["input_evidence_sha256"] == evidence
        assert len({item["review_id"] for item in reviewed["reviews"]}) == 30
        assert all(item["policy_action"] == "proposal_requires_human_review" for item in reviewed["reviews"])
        checks += 4
        for kwargs in ({"score": True, "category": "motion"}, {"score": 0, "category": "other"},
                       {"score": 5, "category": "run_policy"}):
            try:
                review.save_review("broker-A", note="", root=base, **kwargs)
            except ValueError:
                checks += 1
            else:
                raise AssertionError("Invalid feedback accepted")
        assert review.read_case("../../escape", root=base) is None
        assert not list(base.rglob("*.tmp"))
        summary = review.export_feedback_summary(root=base)
        assert summary["authority"] == "untrusted_evidence_only" and len(summary["cases"]) == 1
        checks += 3
        # Run the actual Generator status integration without requiring a host.
        tree = ast.parse((ROOT / "HMBSeedanceGeneration.py").read_text(encoding="utf-8"))
        node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "HMBSeedanceGeneration")
        method = next(item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "_record_review_stage")
        module = ast.Module(body=[method], type_ignores=[])
        clock = SimpleNamespace(monotonic=lambda: 10.)
        namespace = {"time": clock, "_review": review, "logger": SimpleNamespace(warning=lambda *args: None),
                     "_my_box_node": SimpleNamespace(is_selected=lambda node: bool(getattr(node, "_fixture_my_box", False)))}
        exec(compile(ast.fix_missing_locations(module), "<actual-generator-review-stage>", "exec"), namespace)
        runner = SimpleNamespace(_hmb_review_case_id=case_id, _hmb_review_stage="preparing",
                                 _hmb_review_stage_started=7., _hmb_review_stage_seconds={})
        original_update = review.update_case
        with patch.object(review, "update_case", side_effect=lambda *args, **kwargs: original_update(*args, root=base, **kwargs)):
            namespace["_record_review_stage"](runner, "succeeded", "broker-A")
            namespace["_record_review_stage"](runner, "succeeded", "broker-A")
        assert review.read_case("broker-A", root=base)["stage_elapsed_seconds"] == {"preparing": 3.}
        assert review.read_case("broker-A", root=base)["status"] == "succeeded"
        assert review.read_case("broker-A", root=base)["input_evidence_sha256"] == evidence
        checks += 3
        # Private Only results must never mutate a production casecard. The
        # actual My Box selector/controller is exercised by the SDK regression.
        with patch.object(review, "update_case") as publish:
            runner._fixture_my_box = True
            namespace["_record_review_stage"](runner, "failed", "broker-A")
            runner._fixture_my_box = False
            namespace["_record_review_stage"](runner, "failed", "job-mybox-" + "a" * 32)
            runner._hmb_my_box_controller_instance = SimpleNamespace(_busy=True)
            namespace["_record_review_stage"](runner, "failed", "broker-A")
            publish.assert_not_called()
            del runner._hmb_my_box_controller_instance
        assert runner._hmb_review_stage == "succeeded"
        checks += 4
        review.update_case("broker-A", status="succeeded", stage_elapsed_seconds={"unrelated_new_run": 900.}, root=base)
        assert review.read_case("broker-A", root=base)["stage_elapsed_seconds"] == {"preparing": 3.}
        checks += 1
        # The upload is a whitelist of supplemental identities, not the private
        # casecard or a client replacement of the Broker's stored prompt.
        projected = review.public_evidence(review.read_case("broker-A", root=base))
        assert projected == review.public_evidence(projected)
        assert projected["references"][0]["content_sha256"] == local["content_sha256"]
        assert projected["shot"]["shot_uuid"] == "shot-A"
        assert projected["shot"]["name"] == "컷 01 · 점프 🎬"
        assert projected["client_prompt_sha256"] == record["prompt_sha256"]
        assert not any(value in json.dumps(projected) for value in (str(base), "SECRET", "private.invalid", "exact submitted prompt"))
        assert set(projected) == {"schema", "version", "case_id", "input_evidence_sha256", "client_prompt_sha256",
                                  "project_id", "project_name",
                                  "build", "shot", "settings", "references", "agent_observation"}
        hostile = {**projected, "authorization": "SECRET", "prompt": "overwrite", "broker_server_url": "https://private.invalid",
                   "agent_observation": {"coverage": None, "skips": "https://private.invalid", "groups": {"url": "secret"}}}
        clean = review.public_evidence(hostile)
        assert not any(value in json.dumps(clean) for value in ("SECRET", "overwrite", "private.invalid"))
        assert clean["agent_observation"]["coverage"] == []
        checks += 8
        # Snapshot names survive caller mutation and repeated public projection.
        for name in ("Shot 1", "컷 02 · 카메라 고정 🎬", "é", "e\u0301", "가" * 128):
            source = {"shot_uuid": "shot-snapshot", "name": name}
            captured = review.capture_inputs({"_hmb_generation_origin": source})
            source["name"] = "Current renamed slot"
            card = review.public_evidence({"inputs": captured, "agent_observation": {}})
            assert card["shot"]["name"] == name
            assert review.public_evidence(card) == card
            checks += 2
        for name in (None, True, 42, {}, [], "", "   ", "가" * 129, "C:\\private\\a.mb",
                     "/tmp/private", "https://private.invalid", "file://private", "data:secret",
                     "label\nprivate", "label\x7f", "Bearer TOKEN", "api_key=TOKEN", "password: TOKEN"):
            card = review.public_evidence({"inputs": {"generation_origin": {"name": name, "number": 1}}})
            assert "name" not in card["shot"] and card["shot"]["number"] == 1
            checks += 1
        bound_digest = "e" * 64
        review.mark_server_sync("broker-A", status="synced", evidence_sha256=bound_digest, root=base)
        for state in ("pending", "login_required", "failed"):
            review.mark_server_sync("broker-A", status=state, root=base)
            assert review.read_case("broker-A", root=base)["server_sync"]["evidence_sha256"] == bound_digest
            assert review.read_case("broker-A", root=base)["input_evidence_sha256"] == evidence
            checks += 2
        # Oversized JSON numbers and non-finite values are invalid evidence,
        # while authored zero and OFF remain valid. Optional review sync must
        # not crash merely because a stored observation has a huge integer.
        for invalid_number in (10**1000, -(10**1000), float("nan"), float("inf"), float("-inf")):
            bounded = review.public_evidence({
                "inputs": {"settings": {"seed": invalid_number, "duration": 0, "generate_audio": False},
                           "references": [{"bytes": invalid_number, "index": 0}]},
                "agent_observation": {"budget_summary": {"encoded_bytes_prepared": invalid_number},
                                      "coverage": [{"requested_seek_seconds": invalid_number}]},
            })
            assert "seed" not in bounded["settings"]
            assert bounded["settings"]["duration"] == 0 and bounded["settings"]["generate_audio"] is False
            assert "bytes" not in bounded["references"][0] and bounded["references"][0]["index"] == 0
            assert bounded["agent_observation"]["budget_summary"]["encoded_bytes_prepared"] is None
            assert bounded["agent_observation"]["coverage"][0]["requested_seek_seconds"] is None
            json.dumps(bounded, allow_nan=False)
            checks += 6
        timing_id = review.start_case("timing-client", {}, "unchanged", {}, {}, root=base)
        timing = review.update_case("timing-task", case_id=timing_id, stage_elapsed_seconds={
            "valid": 1.23456, "zero": 0, "huge": 10**1000, "nan": float("nan"),
            "inf": float("inf"), "bool": True,
        }, root=base)
        assert timing["stage_elapsed_seconds"] == {"valid": 1.2346, "zero": 0.0}
        assert review.read_case("timing-task", root=base)["submitted_prompt"] == "unchanged"
        json.dumps(timing, allow_nan=False)
        checks += 3
        review.bind_task_origin("broker-A", "https://old.example", root=base)
        review.bind_task_origin("broker-A", "https://old.example/", root=base)
        assert review.task_origin("broker-A", root=base) == "https://old.example"
        for origin in ("https://new.example", "https://user:SECRET@old.example", "https://old.example/?token=SECRET"):
            try:
                review.bind_task_origin("broker-A", origin, root=base)
            except ValueError:
                checks += 1
            else:
                raise AssertionError("Task origin was reassigned or acquired credentials")
        assert "old.example" not in json.dumps(review.public_evidence(review.read_case("broker-A", root=base)))
        checks += 2
        review.mark_server_sync("broker-A", status="pending", root=base)
        review.mark_server_sync("broker-A", status="synced", evidence_sha256=review._digest(projected), root=base)
        assert review.read_case("broker-A", root=base)["server_sync"]["status"] == "synced"
        web = {"task_id": "broker-A", "client_review_id": "web-review-1", "score": 5, "category": "identity", "note": "From web"}
        cached = review.cache_server_feedback("broker-A", [web, web], has_more=True, root=base)
        assert len(cached["items"]) == 1 and cached["has_more"]
        assert review.read_server_feedback("broker-A", root=base)["items"][0]["note"] == "From web"
        assert len(review.read_case("broker-A", root=base)["reviews"]) == 30
        for invalid in ({**web, "task_id": "different"}, {**web, "score": True}, {**web, "category": "sign_policy"}):
            try:
                review.cache_server_feedback("broker-A", [invalid], root=base)
            except ValueError:
                checks += 1
            else:
                raise AssertionError("Foreign or invalid feedback accepted")
        assert review.read_server_feedback("broker-A", root=base) == cached
        assert review.read_server_feedback("different", root=base) is None
        checks += 6
    print(f"PASS: Task casecard regression ({checks} checks; 30 concurrent local feedback writes).")


if __name__ == "__main__":
    main()
