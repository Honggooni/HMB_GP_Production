from __future__ import annotations

import asyncio
import copy
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import HMBAnalysisAgent as analysis


class PromptFixture:
    def __init__(self, path):
        self.path = path
        self.source_id = "video:sample"
        self.reference = "@video2"

    def _hmb_analysis_catalog(self):
        return {"channel_uuid": "channel", "shots": [
            {"number": i, "shot_uuid": f"shot-{i}", "name": f"Shot {i}"} for i in range(1, 6)]}

    def _hmb_analysis_sources_for(self, *, channel_uuid, shot_uuid):
        return [{"kind": "video", "source_id": self.source_id, "name": "example.mov"}]

    def _hmb_analysis_reference_for(self, *, channel_uuid, shot_uuid, kind, source_id):
        if channel_uuid == "channel" and shot_uuid in {"shot-1", "shot-2"} and kind == "video" and source_id == self.source_id:
            return {"kind": kind, "source_id": source_id, "name": "example.mov", "path": str(self.path),
                    "shot_reference": self.reference}
        return {}

    _hmb_analysis_upstream_sources_for = _hmb_analysis_sources_for
    _hmb_analysis_upstream_reference_for = _hmb_analysis_reference_for

    def _hmb_analysis_originals_for(self, *, channel_uuid, shot_uuid):
        if channel_uuid != "channel" or shot_uuid not in {"shot-1", "shot-2"}:
            return []
        return [
            {"kind": "video", "path": str(self.path), "source_id": self.source_id,
             "shot_reference": "@video2", "name": "example.mov"},
            {"kind": "audio", "path": str(self.path.with_suffix(".wav")), "source_id": "audio:fixture",
             "name": "example.wav", "start_seconds": 1, "end_seconds": 3},
        ]


class AnalysisNodeRegression(unittest.TestCase):
    def setUp(self):
        working = tempfile.TemporaryDirectory()
        self.addCleanup(working.cleanup)
        self.path = Path(working.name) / "sample.mov"
        self.path.write_bytes(b"synthetic path for the scope fixture")
        self.prompt = PromptFixture(self.path)
        self.prompt._hmb_apply_analysis_fields = mock.Mock(return_value=True)
        self.node = self.make_node()
        self.nodes = [self.prompt, self.node]
        registry = {"HMBPromptLibrary": PromptFixture, "HMBAnalysisAgent": analysis.HMBAnalysisAgent}
        for patch in (
            mock.patch.object(analysis, "_registered_node_class", side_effect=registry.get),
            mock.patch.object(analysis, "_same_flow_nodes", side_effect=lambda node: ("flow", self.nodes) if node in self.nodes else ("", [])),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    @staticmethod
    def make_node():
        node = object.__new__(analysis.HMBAnalysisAgent)
        node._lock = threading.RLock()
        node._active = ("", "")
        node._slots = {}
        node._revision = 0
        node._job = None
        node._model_choices = {}
        node._sources = []
        node._selected_source = {}
        node._preview_request = None
        node._preview_task = None
        node._hmb_node_deleted = False
        node._syncing = False
        node._publish = mock.Mock()
        node._hmb_schedule_analysis_refresh = mock.Mock()
        return node

    def pick(self, shot="shot-1", guidance=""):
        return self.node._hmb_pick_prompt_reference(self.prompt, channel_uuid="channel", shot_uuid=shot,
            kind="video", source_id=self.prompt.source_id, guidance=guidance)

    def command(self, action, **fields):
        self.node._run_command({"action": action, "channel_uuid": "channel", "shot_uuid": "shot-1",
            "revision": self.node._revision, **fields})

    def context(self, destination, shot="shot-1"):
        return analysis.get_analysis_context(self.prompt, channel_uuid="channel", shot_uuid=shot, destination=destination)

    def set_fixture_result(self, node=None):
        key = analysis._scope("channel", "shot-1")
        node = self.node if node is None else node
        node._slots[key].update(result=analysis._result({"kind": "video", "cache_key": "a" * 64, "source_digest": "b" * 64,
            "model": "gemini-2.5-flash", "range": {"start": 0, "end": 1},
            "observations": {
                "camera": [{"observation": "Fixture camera", "start": 0}],
                "effect_shape": [{"observation": "Fixture effect"}],
                "effect_timing": [{"observation": "Fixture timing", "start": 0.1, "end": 0.8}],
            }}, "video"),
            stamp=analysis._source_stamp(self.prompt._hmb_analysis_reference_for(channel_uuid="channel",
                shot_uuid="shot-1", kind="video", source_id=self.prompt.source_id)),
            applied=True)

    def test_pair_assigns_free_role_and_rejects_duplicate_role_change(self):
        self.node._role = None
        other = self.make_node()
        other._role = None
        self.nodes.append(other)
        self.node._ensure_registered_role()
        other._ensure_registered_role()
        self.assertEqual(self.node._role_options(), ("after", ["after"], False))
        self.assertEqual(other._role_options(), ("before", ["before"], False))
        with self.assertRaises(analysis._AnalysisStateError):
            other._run_command({"action": "set_role", "role": "after", "revision": other._revision})
        self.assertEqual(other._role, "before")

    def test_page_switch_uses_prepared_exact_shot_without_original_io(self):
        self.assertTrue(self.pick())
        self.set_fixture_result()
        saved = copy.deepcopy(self.node._slots)
        prepared = self.prompt._hmb_analysis_originals_for(channel_uuid="channel", shot_uuid="shot-1")
        for role, getter in (("after", "_hmb_analysis_preview_sources_for"),
                             ("before", "_hmb_analysis_upstream_preview_sources_for")):
            self.node._role = role
            with mock.patch.object(self.prompt, getter, create=True, return_value=prepared) as display, \
                 mock.patch.object(self.node, "_resolve_source", side_effect=AssertionError("page hydrated originals")), \
                 mock.patch.object(analysis, "_source_stamp", side_effect=AssertionError("page performed file IO")), \
                 mock.patch.object(self.node, "_queue_preview"):
                self.command("select_shot")
                display.assert_called_once_with(channel_uuid="channel", shot_uuid="shot-1")
                self.assertEqual(self.node._selected_source["source_id"], self.prompt.source_id)
                self.assertEqual(self.node._slots, saved)

    def test_missing_prepared_page_does_not_destroy_saved_result(self):
        self.assertTrue(self.pick())
        self.set_fixture_result()
        saved = copy.deepcopy(self.node._slots)
        with mock.patch.object(self.prompt, "_hmb_analysis_preview_sources_for", create=True, return_value=[]), \
             mock.patch.object(self.node, "_resolve_source", side_effect=AssertionError("page hydrated originals")):
            self.command("select_shot")
        self.assertEqual(self.node._selected_source, {})
        self.assertEqual(self.node._slots, saved)

    def test_preview_cache_is_exact_role_path_stamp_and_range(self):
        self.assertTrue(self.pick())
        slot = self.node._slots[analysis._scope("channel", "shot-1")]
        prepared = self.prompt._hmb_analysis_originals_for(channel_uuid="channel", shot_uuid="shot-1")
        self.node._role = "after"
        identity = (("channel", "shot-1"), "after", "video", self.prompt.source_id, str(self.path),
                    tuple(slot["stamp"] or slot["original_stamp"]), slot["start"], slot["end"])
        self.node._preview_cache = {identity: {"preview_url": "fixture.mp4", "frame_count": 240, "frame_rate": 24}}
        with mock.patch.object(self.prompt, "_hmb_analysis_preview_sources_for", create=True, return_value=prepared), \
             mock.patch.object(self.node, "_queue_preview") as queue:
            self.command("select_shot")
            queue.assert_not_called()
            self.assertEqual(self.node._selected_source["frame_count"], 240)
            # A replaced original at the same path must never reuse the preview.
            slot["stamp"] = ["changed"]
            self.command("select_shot")
            queue.assert_called_once()

    def test_prepared_page_never_authorizes_missing_original_analysis(self):
        self.assertTrue(self.pick())
        prepared = self.prompt._hmb_analysis_originals_for(channel_uuid="channel", shot_uuid="shot-1")
        with mock.patch.object(self.prompt, "_hmb_analysis_preview_sources_for", create=True, return_value=prepared), \
             mock.patch.object(self.prompt, "_hmb_analysis_reference_for", return_value={}), \
             mock.patch.object(self.node, "_start_analysis") as start:
            self.command("select_shot")
            with self.assertRaises(analysis._AnalysisStateError):
                self.command("analyze", confirmed_paid=True)
            start.assert_not_called()

    def test_before_cached_analysis_fills_exact_shot_without_changing_after_delivery(self):
        self.assertTrue(self.pick())
        self.set_fixture_result()
        self.command("delivery", results_only=True, categories=["camera"])
        before = self.make_node()
        before._role = "before"
        self.nodes.append(before)
        self.assertTrue(before._hmb_pick_prompt_reference(self.prompt, channel_uuid="channel",
            shot_uuid="shot-1", kind="video", source_id=self.prompt.source_id))
        self.set_fixture_result(before)
        key = analysis._scope("channel", "shot-1")
        slot = before._slots[key]
        slot["model"] = slot["result"]["model"] = "gemini-4-argon"
        before._start_analysis(self.prompt, "channel", "shot-1", copy.deepcopy(slot),
            before._resolve_source(self.prompt, "channel", "shot-1", slot), {"confirmed_paid": True})
        channel, shot, fields = self.prompt._hmb_apply_analysis_fields.call_args.args
        self.assertEqual((channel, shot), ("channel", "shot-1"))
        self.assertIn("Fixture camera", fields["VIDEO_VFX"])
        self.assertIn("Fixture effect", fields["VIDEO_VFX"])
        self.assertEqual(fields["PRESERVED_TEXT"], "")
        self.assertTrue(before._slots[key]["prompt_applied"])
        authored = "[Dialogue]  Exact punctuation!  "
        before._run_command({"action": "set_field", "field": "PRESERVED_TEXT", "text": authored,
            "channel_uuid": channel, "shot_uuid": shot, "revision": before._revision})
        self.assertEqual(self.prompt._hmb_apply_analysis_fields.call_args.args[-1]["PRESERVED_TEXT"], authored)
        restored = analysis._normalize_slot(before._slots[key])
        self.assertEqual(restored["field_overrides"]["PRESERVED_TEXT"], authored)
        self.assertEqual([row["category"] for row in self.context("agent")["items"]], ["camera"])
        self.assertEqual(analysis.get_analysis_originals(self.prompt, channel_uuid=channel, shot_uuid=shot), [])
        self.nodes.remove(self.node)
        self.assertEqual(self.context("agent"), {})
        self.assertEqual(len(analysis.get_analysis_originals(self.prompt, channel_uuid=channel, shot_uuid=shot)), 2)

    def test_legacy_hydration_and_conflict_recovery_preserve_saved_slots(self):
        self.assertTrue(self.pick())
        self.set_fixture_result()
        legacy = self.make_node()
        legacy._role = "before"
        payload = {"schema": analysis._SCHEMA, "version": 1, "active": ["channel", "shot-1"],
                   "slots": copy.deepcopy(self.node._slots)}
        with mock.patch.object(analysis.DataNode, "set_parameter_value"):
            legacy.set_parameter_value(analysis.STATE, payload, initial_setup=True)
        self.assertEqual(legacy._role, "after")
        self.nodes.append(legacy)
        self.assertEqual(legacy._role_options(), ("after", ["after", "before"], True))
        self.assertEqual(self.context("agent"), {})
        saved = copy.deepcopy(legacy._slots)
        legacy._run_command({"action": "set_role", "role": "before", "revision": legacy._revision})
        self.assertEqual(legacy._slots, saved)
        self.assertTrue(self.context("agent"))
        self.prompt._hmb_apply_analysis_fields.assert_not_called()

    def test_before_source_result_survives_switch_to_after_catalog_without_that_source(self):
        self.node._role = "before"
        self.assertTrue(self.pick())
        self.set_fixture_result()
        saved = copy.deepcopy(self.node._slots)
        with mock.patch.object(self.prompt, "_hmb_analysis_reference_for", return_value={}):
            self.node._run_command({"action": "set_role", "role": "after", "revision": self.node._revision})
            self.node._refresh_sources()
            self.assertEqual(self.context("agent"), {})
        self.assertEqual(self.node._slots, saved)

    def test_retired_explicit_model_restores_as_default_without_losing_result(self):
        self.assertTrue(self.pick(guidance="Saved instructions"))
        self.set_fixture_result()
        slot = self.node._slots[analysis._scope("channel", "shot-1")]
        slot["model"] = "gemini-2.5-flash"
        normalized = analysis._normalize_slot(slot)
        self.assertEqual(normalized["model"], "")
        self.assertEqual(normalized["result"], slot["result"])
        self.assertEqual(normalized["stamp"], slot["stamp"])
        self.assertEqual(normalized["guidance"], "Saved instructions")
        self.assertTrue(normalized["applied"])

    def test_exact_shot_and_selected_destinations(self):
        self.assertTrue(self.pick(guidance="Use only the effect cues"))
        self.set_fixture_result()
        self.assertEqual([item["category"] for item in self.context("agent")["items"]],
                         ["camera", "effect_shape", "effect_timing"])
        self.command("delivery", categories=["effect_shape", "effect_timing"])
        agent = self.context("agent")
        self.assertEqual([item["category"] for item in agent["items"]], ["effect_shape", "effect_timing"])
        self.assertEqual(agent["items"][1]["start"], 0.1)
        self.assertNotIn("guidance", agent)
        self.assertNotIn("path", agent)
        self.assertEqual(agent["source_reference"], "@video2")
        self.assertEqual(agent["source_id"], self.prompt.source_id)
        self.assertEqual(agent["analysis_status"], "completed")
        self.assertEqual(self.context("generator"), {})
        self.assertEqual(self.context("agent", "shot-2"), {})
        self.command("delivery", categories=["camera"], send_original=True)
        self.assertEqual(self.context("agent")["items"][0]["start"], 0)
        self.assertEqual(self.context("generator"), {})
        self.assertTrue(analysis.get_analysis_original(self.prompt, channel_uuid="channel", shot_uuid="shot-1"))
        slot = self.node._slots[analysis._scope("channel", "shot-1")]
        old_generator_only = dict(slot, send_agent=False, send_original=False, send_generator=True)
        migrated = analysis._normalize_slot(old_generator_only)
        self.assertFalse(migrated["applied"])
        self.assertEqual(migrated["result"], slot["result"])
        self.command("delivery", categories=["camera"], send_agent=False, send_original=False)
        self.assertEqual(self.context("agent"), {})
        self.assertFalse(analysis.get_analysis_original(self.prompt, channel_uuid="channel", shot_uuid="shot-1"))

    def test_edit_selected_results_and_clear_selection(self):
        from _hmb_analysis_delivery import analysis_delivery_context

        self.assertTrue(self.pick())
        self.set_fixture_result()
        self.command("delivery", categories=["camera"], result_text_categories=["effect_shape"],
                     result_text="Revised effect\nSecond line")
        self.assertEqual(self.context("agent")["items"][0]["category"], "camera")
        self.command("delivery", categories=["effect_shape"])
        slot = self.node._slots[analysis._scope("channel", "shot-1")]
        self.assertEqual(analysis._normalize_slot(slot), slot)
        self.assertEqual(analysis._result_editor_text(slot), "Revised effect\nSecond line")
        context = analysis_delivery_context(self.prompt, channel_uuid="channel", shot_uuid="shot-1", destination="agent")
        self.assertEqual(context["edited_result"], "Revised effect\nSecond line")
        self.assertNotIn("items", context)
        self.command("delivery", categories=[])
        self.assertEqual(len(self.context("agent")["items"]), 3)
        self.command("delivery", categories=["effect_shape"])
        self.assertEqual(self.context("agent")["edited_result"], "Revised effect\nSecond line")
        self.command("delivery", categories=["effect_shape"], result_text="")
        self.assertEqual(self.context("agent")["items"][0]["observation"], "Fixture effect")

    def test_analysis_source_reference_follows_reorder_and_results_only(self):
        from _hmb_analysis_delivery import analysis_delivery_context

        self.assertTrue(self.pick())
        self.set_fixture_result()
        self.command("delivery", categories=["camera"])
        self.prompt.reference = "@video1"
        context = analysis_delivery_context(self.prompt, channel_uuid="channel", shot_uuid="shot-1", destination="agent")
        self.assertEqual(context["source_reference"], "@video1")
        self.assertEqual(context["source_id"], self.prompt.source_id)
        self.assertEqual(context["reference_usage"], "analysis_evidence")
        self.assertTrue(context["original_requested"])
        self.command("delivery", results_only=True, categories=["camera"])
        context = analysis_delivery_context(self.prompt, channel_uuid="channel", shot_uuid="shot-1", destination="agent")
        self.assertFalse(context["original_requested"])
        self.assertEqual(context["analysis_status"], "completed")
        self.assertEqual(analysis.get_analysis_originals(self.prompt, channel_uuid="channel", shot_uuid="shot-1"), [])

    def test_results_only_policy_before_select_and_across_shots(self):
        from _hmb_analysis_delivery import analysis_originals, analysis_results_only, route_analysis_media

        def originals(shot):
            return analysis_originals(self.prompt, channel_uuid="channel", shot_uuid=shot)

        self.command("select_shot")
        expected = originals("shot-1")
        self.assertEqual([item["shot_reference"] for item in expected], ["@video2", "@analysis_original_audio_2"])
        self.assertEqual(expected[1]["start"], 1)
        self.nodes.remove(self.node)
        self.assertEqual(originals("shot-1"), expected)
        self.nodes.append(self.node)
        self.command("delivery", categories=[], results_only=True)
        self.assertTrue(analysis_results_only(self.prompt, channel_uuid="channel", shot_uuid="shot-1"))
        self.assertFalse(analysis_results_only(self.prompt, channel_uuid="channel", shot_uuid="shot-2"))
        self.assertEqual(originals("shot-1"), [])
        self.assertEqual(len(originals("shot-2")), 2)
        key = analysis._scope("channel", "shot-1")
        self.assertTrue(analysis._normalize_slot(self.node._slots[key])["results_only"])
        self.assertTrue(self.pick())
        self.set_fixture_result()
        self.assertEqual(len(self.context("agent")["items"]), 3)
        self.assertEqual(originals("shot-1"), [])
        self.command("clear")
        self.assertEqual(originals("shot-1"), [])
        self.command("delivery", categories=[], results_only=False)
        self.assertEqual(originals("shot-1"), expected)
        with mock.patch.object(self.prompt, "_hmb_analysis_preview_sources_for", create=True,
                               return_value=self.prompt._hmb_analysis_originals_for(channel_uuid="channel", shot_uuid="shot-1")):
            with mock.patch.object(self.prompt, "_hmb_analysis_originals_for", side_effect=AssertionError("hydrated preview")):
                self.assertEqual(analysis_originals(self.prompt, channel_uuid="channel", shot_uuid="shot-1", preview=True),
                                 expected)
        ordinary = str(self.path.with_name("ordinary.mov"))
        original = str(self.path)
        self.assertEqual(route_analysis_media("video", [ordinary, original], [original], expected),
                         ([ordinary, original], []))
        self.assertEqual(route_analysis_media("video", [ordinary, original], [original], []),
                         ([ordinary], [{"shot_reference": "@video1", "provider_reference": "@video1"},
                                       {"shot_reference": "@video2", "provider_reference": None}]))
        self.assertEqual(route_analysis_media("video", [ordinary, original, original], [original], expected),
                         ([ordinary, original], [{"shot_reference": "@video1", "provider_reference": "@video1"},
                                                 {"shot_reference": "@video2", "provider_reference": "@video2"},
                                                 {"shot_reference": "@video3", "provider_reference": "@video2"}]))

    def test_delivery_switch_uses_display_notification_without_loading_sources(self):
        self.assertTrue(self.pick())
        self.set_fixture_result()
        with mock.patch.object(self.node, "_resolve_source", side_effect=AssertionError("unexpected source hydration")):
            with mock.patch.object(self.prompt, "_hmb_notify_analysis_delivery_changed", create=True) as notify:
                self.command("delivery", categories=[], results_only=True)
        notify.assert_called_once_with(channel_uuid="channel", shot_uuid="shot-1")
        self.assertEqual(len(self.context("agent")["items"]), 3)

    def test_video_frame_ranges_survive_restore_and_reach_agent(self):
        from _hmb_analysis_delivery import analysis_delivery_context

        self.assertTrue(self.pick())
        ranges = [{"start": 0, "end": 2}, {"start": 12, "end": 14}]
        self.command("configure", frame_ranges=ranges)
        key = analysis._scope("channel", "shot-1")
        slot = self.node._slots[key]
        self.assertEqual(slot["frame_ranges"], ranges)
        self.assertEqual(analysis._normalize_slot(slot), slot)
        self.set_fixture_result()
        slot["result"]["frame_ranges"] = ranges
        slot["result"]["observations"]["camera"][0].update(start_frame=0, end_frame=2)
        context = analysis_delivery_context(self.prompt, channel_uuid="channel", shot_uuid="shot-1", destination="agent")
        self.assertEqual(context["source_frame_ranges"], ranges)
        self.assertNotIn("source_range_seconds", context)
        self.assertEqual(context["items"][0]["start_source_frame"], 0)
        self.assertIn("0–2프레임", analysis._result_editor_text(slot))
        with self.assertRaises(analysis._AnalysisStateError):
            self.command("configure", time_ranges=[{"start": 0, "end": 1}])

    def test_whole_video_ignores_but_retains_authored_ranges(self):
        self.assertTrue(self.pick())
        key = analysis._scope("channel", "shot-1")
        ranges = [{"start": 1, "end": 8}]
        self.command("configure", frame_ranges=ranges)
        self.set_fixture_result()
        result = dict(self.node._slots[key]["result"], model="gemini-4-argon")
        self.node._slots[key]["model"] = "gemini-4-argon"
        result["frame_ranges"] = ranges
        self.node._slots[key]["result"] = result
        legacy = dict(self.node._slots[key])
        del legacy["full_video"]
        self.assertFalse(analysis._normalize_slot(legacy)["full_video"])
        source = self.prompt._hmb_analysis_reference_for(channel_uuid="channel", shot_uuid="shot-1",
            kind="video", source_id=self.prompt.source_id)
        full_result = {**result, "cache_key": "c" * 64, "range": {"start": 2.0, "end": 7.0}}
        del full_result["frame_ranges"]
        manager = mock.Mock()
        sdk = SimpleNamespace(GriptapeNodes=SimpleNamespace(EventManager=manager))
        with (
            mock.patch.object(self.node, "_resolve_source", return_value={**source, "start_seconds": 2, "end_seconds": 7}),
            mock.patch.dict(sys.modules, {"griptape_nodes.retained_mode.griptape_nodes": sdk}),
            mock.patch.object(asyncio, "run_coroutine_threadsafe", side_effect=lambda task, loop: asyncio.run(task)),
            mock.patch("_hmb_reference_analysis.analyze_reference", side_effect=[full_result, result]) as analyze,
        ):
            manager.return_value.event_loop.is_closed.return_value = False
            self.command("analyze", full_video=True, model="gemini-4-argon", confirmed_paid=True)
            slot = self.node._slots[key]
            self.assertTrue(slot["full_video"])
            self.assertEqual(slot["frame_ranges"], ranges)
            self.assertEqual(slot["result"]["cache_key"], "c" * 64)
            self.assertNotIn("frame_ranges", slot["result"])
            self.assertEqual(analysis._normalize_slot(slot), slot)
            self.assertEqual((analyze.call_args.kwargs["start"], analyze.call_args.kwargs["end"]), (2, 7))
            self.assertNotIn("frame_ranges", analyze.call_args.kwargs)

            self.command("analyze", full_video=False, frame_ranges=ranges, model="gemini-4-argon", confirmed_paid=True)
            slot = self.node._slots[key]
            self.assertFalse(slot["full_video"])
            self.assertEqual(slot["result"]["cache_key"], "a" * 64)
            self.assertEqual(analyze.call_args.kwargs["frame_ranges"], ranges)
            self.assertEqual(analyze.call_count, 2)

        self.command("configure", full_video=True, frame_ranges=[], model="gemini-4-argon")
        self.assertEqual(self.node._slots[key]["frame_ranges"], [])

    def test_original_is_independent_and_checks_current_exact_source(self):
        self.assertTrue(self.pick())
        self.command("apply", categories=[], send_agent=False, send_original=True)
        original = lambda shot: analysis.get_analysis_original(
            self.prompt, channel_uuid="channel", shot_uuid=shot)
        self.assertEqual(original("shot-1"), {"kind": "video", "path": str(self.path),
            "source_id": self.prompt.source_id, "start": None, "end": None, "shot_reference": "@video2"})
        self.assertEqual(original("shot-2"), {})
        self.assertEqual(self.context("agent"), {})
        self.assertEqual(self.context("generator"), {})
        slot = self.node._slots[analysis._scope("channel", "shot-1")]
        self.assertEqual(analysis._normalize_slot(slot), slot)
        legacy = dict(slot, send_original_to_generator=slot["send_original"])
        del legacy["send_original"]
        self.assertEqual(analysis._normalize_slot(legacy), slot)
        self.path.write_bytes(b"original changed after Apply")
        self.assertEqual(original("shot-1"), {})
        self.node._refresh_sources()
        self.assertFalse(slot["send_original"])

    def test_stale_sources_and_duplicates_fail_closed(self):
        self.assertTrue(self.pick())
        self.set_fixture_result()
        self.command("apply", categories=["effect_shape"])
        self.assertTrue(self.context("agent"))
        duplicate = object.__new__(analysis.HMBAnalysisAgent)
        duplicate._hmb_node_deleted = False
        self.nodes.append(duplicate)
        self.assertEqual(self.context("agent"), {})
        self.nodes.remove(duplicate)
        self.path.write_bytes(b"replaced original")
        self.assertEqual(self.context("agent"), {})
        self.assertTrue(self.pick())
        self.assertEqual(self.node._slots[analysis._scope("channel", "shot-1")]["result"], {})

    def test_explicit_paid_request_and_idempotent_repick(self):
        from types import SimpleNamespace
        from _hmb_reference_analysis import analysis_model_settings_digest

        self.assertTrue(self.pick(guidance="Keep this guidance"))
        self.set_fixture_result()
        self.command("delivery", categories=["camera"])
        config = SimpleNamespace(model="gemini-2.5-flash", to_wire=lambda: {"model": "gemini-2.5-flash"})
        self.node._slots[analysis._scope("channel", "shot-1")]["result"]["model_settings_sha256"] = (
            analysis_model_settings_digest(config))
        previous = copy.deepcopy(self.node._slots)
        self.assertTrue(self.pick())
        self.assertEqual(self.node._slots, previous)
        with self.assertRaises(analysis._AnalysisStateError):
            self.command("analyze", guidance="Keep this guidance")
        with self.assertRaises(analysis._AnalysisStateError):
            self.command("analyze", confirmed_paid=True, revision=-1, guidance="Keep this guidance")
        with mock.patch("HMBAgentLibrary.get_same_shot_analysis_model", return_value=config) as resolve:
            self.command("analyze", confirmed_paid=True, guidance="Keep this guidance")
        resolve.assert_called_once_with(self.prompt, channel_uuid="channel", shot_uuid="shot-1", kind="video")
        self.assertEqual(self.node._slots, previous)
        self.assertEqual(self.node._status, "저장된 분석 결과 재사용")


if __name__ == "__main__":
    unittest.main()
