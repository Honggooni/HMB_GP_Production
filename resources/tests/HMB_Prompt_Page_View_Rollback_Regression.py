"""Rejected native writes restore every prepared Prompt selector/cache guard.

Synthetic source metadata only. No model, media file, Broker or live retained
graph is used; the real Prompt setter and baseline/cache methods stay intact.
"""
from __future__ import annotations

from copy import copy, deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
sys.dont_write_bytecode = True
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
import HMBPromptLibrary as prompt

CHANNEL = "11111111-1111-4111-8111-111111111111"
ROWS = [dict(channel_uuid=CHANNEL,
    shot_uuid=f"22222222-2222-4222-8222-{number:012d}", number=number,
    name=f"Original Asset {number}", selected_source_uids=[]) for number in range(1, 6)]


def fixture():
    node = prompt.HMBPromptLibrary(name="Private Prompt page rollback")
    state = prompt._normalize_state(prompt._default_widget_state())
    state["multi_shot_enabled"] = True
    state["shot"] = deepcopy(ROWS[0])
    state["image_asset"]["shot_catalog"] = deepcopy(ROWS)
    state["image_asset"]["shot_catalog_routing"] = dict(
        publisher_instance_uuid="33333333-3333-4333-8333-333333333333",
        channel_uuid=CHANNEL, generation=1, metadata_sha256="a" * 64)
    state = prompt._store_prompt_shot_document(state)
    node._hmb_write_merged_prompt_state(prompt._json_dumps(state))
    original = deepcopy(state)
    original["shot"] = deepcopy(ROWS[2])
    node._hmb_remember_prompt_shot_view(original, "Original saved Shot 3 view")
    return node, state


class PromptPageViewRollback(unittest.TestCase):
    def test_prepared_display_views_preserve_registered_owner_and_picker_authoring_archive(self):
        node, state = fixture()
        key = prompt._prompt_document_key(state["shot"])
        record = {"source": object(), "video_uids": ("exact-video-uid",),
                  "before": {}, "after": None}
        archive = {key: record}
        node._hmb_deleted_picker_authoring = archive
        node._hmb_prompt_shot_views = {}
        raw_before = node._current_state()
        observed = []

        def route(view, selected, **kwargs):
            observed.append((view is not node,
                getattr(view, "_hmb_execution_registered_owner", None) is node))
            # This real helper consumes its shared record only for a canonical
            # editor commit. A display-only shallow copy must retain the owner
            # marker so warming pages cannot consume that authored archive.
            view._restore_deleted_picker_authoring(selected, ["exact-video-uid"])
            return selected, [], [], True, True

        with (mock.patch.object(prompt.HMBPromptLibrary, "_apply_exact_shot_routes",
                  autospec=True, side_effect=route),
              mock.patch.object(prompt, "_build_prompt_package",
                  side_effect=lambda selected: "Ready " + prompt._prompt_document_key(selected["shot"]))):
            changed = node._hmb_prepare_prompt_shot_views()

        self.assertEqual(observed, [(True, True)] * 5)
        self.assertEqual(len(changed), 5)
        self.assertIs(node._hmb_deleted_picker_authoring, archive)
        self.assertIs(archive.get(key), record)
        self.assertEqual(node._current_state(), raw_before)
        self.assertEqual(len(node._hmb_prompt_shot_views), 5)

    def test_exact_execution_facade_uses_own_reader_instead_of_owner_selector_cache(self):
        node, state = fixture()
        view = copy(node)
        selected = deepcopy(state)
        selected["shot"] = deepcopy(ROWS[2])
        view._current_state = lambda: deepcopy(selected)
        self.assertEqual(node._hmb_shot_channel_subscription()["shot_uuid"], ROWS[0]["shot_uuid"])
        self.assertEqual(view._hmb_shot_channel_subscription()["shot_uuid"], ROWS[2]["shot_uuid"])
        self.assertTrue(view._hmb_shot_manager_enabled())
        self.assertEqual(len(view._hmb_prompt_shot_subscriptions()), 5)

    def rejected(self, node, incoming):
        with (mock.patch.object(node, "_hmb_apply_manual_rebind", return_value=False),
              mock.patch.object(node, "_merge_widget_revision_axes", side_effect=lambda value: value),
              mock.patch.object(node, "_widget_state_write_is_stale", return_value=False),
              mock.patch.object(node, "_hmb_filter_prompt_widget_write", side_effect=lambda value: value),
              mock.patch.object(prompt.DataNode, "set_parameter_value",
                  side_effect=RuntimeError("Synthetic native write rejected"))):
            with self.assertRaisesRegex(RuntimeError, "Synthetic native write rejected"):
                node.set_parameter_value(prompt.WIDGET_PARAMETER_NAME, prompt._json_dumps(incoming))

    def test_rejected_catalog_replacement_keeps_original_ready_view_and_selector(self):
        node, state = fixture()
        old = {name: getattr(node, name) for name in (
            "_hmb_last_accepted_widget_state", "_hmb_last_accepted_widget_revisions",
            "_hmb_prompt_selector_projection", "_hmb_prompt_view_catalog_keys",
            "_hmb_last_accepted_manual_rebind_pending")}
        incoming = deepcopy(state)
        incoming["image_asset"]["shot_catalog"][2].update(
            shot_uuid="44444444-4444-4444-8444-000000000003", name="Rejected replacement")
        incoming[prompt.UI_EDIT_REVISION_KEY] += 1
        self.rejected(node, incoming)
        for name, value in old.items():
            self.assertIs(getattr(node, name), value, name)
        self.assertEqual(node._hmb_prompt_selector_state()["shot"], state["shot"])
        self.assertEqual(node._hmb_prompt_shot_view(channel_uuid=CHANNEL,
            shot_uuid=ROWS[2]["shot_uuid"])["visible_prompt"], "Original saved Shot 3 view")
        self.assertFalse(node._hmb_prompt_shot_view(channel_uuid=CHANNEL,
            shot_uuid=incoming["image_asset"]["shot_catalog"][2]["shot_uuid"]))

    def test_rejected_manual_notice_cannot_disable_previously_ready_view(self):
        node, state = fixture()
        incoming = deepcopy(state)
        incoming["manual_rebind"] = dict(required=True, expected_source_digest="b" * 64)
        self.rejected(node, incoming)
        self.assertFalse(node._hmb_last_accepted_manual_rebind_pending[1])
        self.assertTrue(node._hmb_prompt_shot_view(channel_uuid=CHANNEL,
            shot_uuid=ROWS[2]["shot_uuid"]))

    def test_legacy_absent_projection_fields_remain_absent_guards_after_rejection(self):
        node, state = fixture()
        for name in ("_hmb_prompt_selector_projection", "_hmb_prompt_view_catalog_keys",
                     "_hmb_last_accepted_manual_rebind_pending"):
            node.__dict__.pop(name, None)
        self.rejected(node, state)
        self.assertIsNone(node._hmb_prompt_selector_projection)
        self.assertIsNone(node._hmb_prompt_view_catalog_keys)
        self.assertIsNone(node._hmb_last_accepted_manual_rebind_pending)
        self.assertTrue(node._hmb_prompt_shot_view(channel_uuid=CHANNEL,
            shot_uuid=ROWS[2]["shot_uuid"]))

    def test_same_visible_page_with_inactive_document_edit_is_not_presentation_only(self):
        node, state = fixture()
        field = next(iter(prompt.TEXT_FIELD_DEFAULTS))
        inactive = deepcopy(state)
        inactive["shot"] = deepcopy(ROWS[2])
        inactive["text"][field] = "Original inactive literal"
        inactive = prompt._store_prompt_shot_document(inactive)
        state["shot_documents"] = inactive["shot_documents"]
        node._hmb_write_merged_prompt_state(prompt._json_dumps(state))
        node._hmb_remember_prompt_shot_view(inactive, "Original inactive public page")
        incoming = deepcopy(state)
        key = prompt._prompt_document_key(ROWS[2])
        stored = prompt._parse_state(incoming["shot_documents"][key])
        stored["text"][field] = "New inactive literal from merged pending UI edit"
        incoming["shot_documents"][key] = prompt._json_dumps(stored)
        incoming[prompt.UI_EDIT_REVISION_KEY] += 1
        with mock.patch.object(node, "_schedule_prompt_sync") as schedule:
            node.set_parameter_value(prompt.WIDGET_PARAMETER_NAME, prompt._json_dumps(incoming))
        schedule.assert_called_once_with(source_burst=False)
        self.assertEqual(prompt._parse_state(node._current_state()["shot_documents"][key])["text"][field],
            "New inactive literal from merged pending UI edit")

    def test_unchanged_active_output_refreshes_only_edited_inactive_consumer_and_isolates_failure(self):
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        node, state = fixture()
        edited = deepcopy(state)
        edited["shot"] = deepcopy(ROWS[2])
        edited["text"][next(iter(prompt.TEXT_FIELD_DEFAULTS))] = "Edited exact inactive Shot 3"
        key = prompt._prompt_document_key(ROWS[2])
        node._hmb_last_prompt_output = "Stable active Shot 1"
        node._hmb_last_machine_prompt_output = "Stable private active Shot 1"
        node._hmb_last_prompt_semantic_fingerprint = "stable-active-fingerprint"
        node._hmb_current_shot_images = []
        node._hmb_current_shot_videos = []
        node._hmb_pending_prompt_notification = None
        node.parameter_output_values.update(PROMPT_OUT="Stable active Shot 1",
            SHOT_IMAGE_OUT=[], SHOT_VIDEO_OUT=[])
        observed = []
        def hydrate(source, parameter):
            self.assertIs(source, node)
            self.assertEqual(parameter, "PROMPT_OUT")
            observed.append(node._hmb_prompt_shot_view(channel_uuid=CHANNEL,
                shot_uuid=ROWS[2]["shot_uuid"])["visible_prompt"])
        failed = SimpleNamespace(lock=False,
            _hmb_shot_channel_subscription=mock.Mock(side_effect=RuntimeError("Deleted target")),
            _hmb_hydrate_shot_prompt_from_source=mock.Mock())
        target = SimpleNamespace(lock=False, _hmb_shot_channel_subscription=lambda: ROWS[2],
            _hmb_hydrate_shot_prompt_from_source=mock.Mock(side_effect=hydrate))
        other = SimpleNamespace(lock=False, _hmb_shot_channel_subscription=lambda: ROWS[1],
            _hmb_hydrate_shot_prompt_from_source=mock.Mock())
        locked = SimpleNamespace(lock=True, _hmb_shot_channel_subscription=lambda: ROWS[2],
            _hmb_hydrate_shot_prompt_from_source=mock.Mock())
        foreign = SimpleNamespace(lock=False, _hmb_shot_channel_subscription=lambda: ROWS[2],
            _hmb_hydrate_shot_prompt_from_source=mock.Mock())
        edges = [SimpleNamespace(source_node=node, target_node=item)
            for item in (failed, other, locked, target, target)]
        edges.append(SimpleNamespace(source_node=object(), target_node=foreign))
        connections = SimpleNamespace(get_outgoing_connections_from_parameter=lambda *args: edges)
        flow = SimpleNamespace(get_connections=lambda: connections)
        def prepare():
            node._hmb_remember_prompt_shot_view(edited, "Ready edited inactive Shot 3")
            return {key}
        before_outputs = deepcopy(dict(node.parameter_output_values))
        with (mock.patch.object(GriptapeNodes, "FlowManager", return_value=flow),
              mock.patch.object(node, "_compile_current_prompt_pair", return_value=(state,
                  "Stable active Shot 1", "Stable private active Shot 1", "stable-active-fingerprint")),
              mock.patch.object(node, "_hmb_prepare_prompt_shot_views", side_effect=prepare),
              mock.patch.object(node, "_hmb_prompt_shot_document", side_effect=AssertionError("Display built execution document")),
              mock.patch.object(prompt, "_stage_and_notify_prompt_output", side_effect=AssertionError("Display republished unchanged active output"))):
            node._sync_prompt_output_from_state()
        self.assertEqual(observed, ["Ready edited inactive Shot 3"])
        target._hmb_hydrate_shot_prompt_from_source.assert_called_once_with(node, "PROMPT_OUT")
        for item in (failed, other, locked, foreign):
            item._hmb_hydrate_shot_prompt_from_source.assert_not_called()
        self.assertEqual(dict(node.parameter_output_values), before_outputs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
