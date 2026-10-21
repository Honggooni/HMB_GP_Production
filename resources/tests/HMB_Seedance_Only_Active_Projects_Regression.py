"""Only's two active projects and separate personal My Box choice.

The existing synthetic graph imports the actual Generator implementation.
No account token, live API, provider request, user workflow or media is used.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
import HMB_Seedance_Only_Project_Selection_Regression as fixture
from _hmb_project import PROJECTS, resolve_project
from _hmb_my_box import MY_BOX_LABEL

t, Graph, Node = fixture.t, fixture.Graph, fixture.Node
ACTIVE = ("superwings12", "katuri8")
EXPECTED_CHOICES = [t.ONLY_PROJECT_UNSELECTED, *(PROJECTS[key]["project_name"] for key in ACTIVE), MY_BOX_LABEL]


class OnlyActiveProjects(unittest.TestCase):
    def setUp(self):
        # Windows asyncio creates an internal loopback socket pair. Create it
        # before blocking every socket connect; the tests still issue no HTTP.
        self.loop = asyncio.new_event_loop()
        self.addCleanup(self.loop.close)
        stack = fixture.project.ExitStack()
        stack.enter_context(mock.patch.object(t._review, "bind_task_origin"))
        stack.enter_context(mock.patch.object(t._review, "bind_task_project"))
        stack.enter_context(mock.patch.object(t, "_broker_log_transport_error"))
        stack.enter_context(mock.patch.object(t, "_broker_load_token",
            side_effect=AssertionError("Active choices must not read authentication tokens")))
        for target in ("socket.create_connection", "socket.socket.connect"):
            stack.enter_context(mock.patch(target,
                side_effect=AssertionError("Active choices must not contact a real API")))
        stack.enter_context(mock.patch.object(t.urllib.request.OpenerDirector, "open",
            side_effect=AssertionError("Active choices must not open HTTP requests")))
        self.addCleanup(stack.close)

    def tearDown(self):
        while fixture.base.TEMPORARIES:
            fixture.base.TEMPORARIES.pop().cleanup()

    def test_new_only_selector_has_two_active_project_names_in_production_order(self):
        node = t.HMBSeedanceGeneration(name="Only active project parameter fixture")
        parameter = node.get_parameter_by_name(t.ONLY_PROJECT_PARAMETER)
        self.assertEqual(parameter.ui_options["simple_dropdown"], EXPECTED_CHOICES)
        find_traits = getattr(parameter, "find_elements_by_type", None)
        traits = find_traits(t.Options) if callable(find_traits) else list(parameter.traits)
        self.assertEqual(len(traits), 1)
        self.assertEqual(list(traits[0].choices), EXPECTED_CHOICES)
        self.assertEqual(node.get_parameter_value(t.ONLY_PROJECT_PARAMETER), t.ONLY_PROJECT_UNSELECTED)
        self.assertEqual(EXPECTED_CHOICES, ["Select Project", "슈퍼윙즈12", "까투리8", "My Box"])
        self.assertEqual(EXPECTED_CHOICES.count(MY_BOX_LABEL), 1)
        self.assertNotIn(MY_BOX_LABEL, PROJECTS)
        self.assertFalse(any(row["project_name"] == MY_BOX_LABEL for row in PROJECTS.values()))

    def test_saved_active_ids_names_and_supported_aliases_resolve_without_network(self):
        aliases = {"superwings12": ("superwings12", "슈퍼윙즈12", "슈퍼윙스12", "Super Wings 12"),
                   "katuri8": ("katuri8", "까투리8", "Katuri8")}
        for project_id, values in aliases.items():
            for value in values:
                with self.subTest(project=project_id, saved=value):
                    node = Node(); node.select(value)
                    before = deepcopy(node.parameter_values)
                    self.assertEqual(node._selected_only_project(), {
                        "project_id": project_id, "project_name": PROJECTS[project_id]["project_name"]})
                    graph = Graph(node)
                    with graph.context():
                        snapshot = node._capture_imageasset_project_selection()
                    self.assertEqual(snapshot["project"]["project_id"], project_id)
                    self.assertEqual(snapshot["schema"], t.ONLY_PROJECT_SELECTION_SCHEMA)
                    self.assertEqual(node.parameter_values, before)
                    self.assertEqual(node.transport.calls, [])
                    self.assertEqual(node.bridge.posts, [])

    def test_inactive_dinoster_only_selection_fails_before_auth_upload_or_create(self):
        for value in ("dinoster5", "Dinoster5", "다이노스터", "다이노스터5"):
            with self.subTest(saved=value):
                node = Node(fixture.values_for(t.TASK_VIDEO_EDITING)); node.select(value)
                authored = deepcopy(node.parameter_values)
                node._ensure_broker_connected = mock.AsyncMock(side_effect=AssertionError("Authentication started"))
                with self.assertRaises(ValueError):
                    node._selected_only_project()
                with Graph(node).context(), self.assertRaises(ValueError):
                    self.loop.run_until_complete(node._process_generation_impl())
                node._ensure_broker_connected.assert_not_awaited()
                for key in ("only_project", "prompt", "resolution", "task", "reference_images", "video_references"):
                    self.assertEqual(node.parameter_values.get(key), authored.get(key))
                self.assertEqual(node.transport.calls, [])
                self.assertEqual(node.bridge.posts, [])
                self.assertEqual(node.upload_calls, 0)
                self.assertEqual(node.saved, [])

    def test_missing_selection_still_blocks_unconnected_only_before_broker(self):
        for value in (None, "", t.ONLY_PROJECT_UNSELECTED):
            with self.subTest(value=value):
                node = Node(fixture.values_for(t.TASK_VIDEO_EXTENSION)); node.select(value)
                self.assertEqual(node._selected_only_project(), {})
                node._ensure_broker_connected = mock.AsyncMock(side_effect=AssertionError("Authentication started"))
                with Graph(node).context(), self.assertRaises(t._ProjectSelectionRequired):
                    self.loop.run_until_complete(node._process_generation_impl())
                node._ensure_broker_connected.assert_not_awaited()
                self.assertEqual(node.transport.calls, [])
                self.assertEqual(node.bridge.posts, [])
                self.assertEqual(node.upload_calls, 0)

    def test_historical_dinoster_identity_and_evidence_remain_readable(self):
        self.assertEqual(set(PROJECTS), {"dinoster5", "superwings12", "katuri8"})
        expected = {"project_id": "dinoster5", "project_name": "다이노스터"}
        for value in ("dinoster5", "다이노스터", expected):
            with self.subTest(value=value):
                actual = resolve_project(value, default_legacy=False)
                self.assertEqual({key: actual[key] for key in expected}, expected)
        evidence = t._review.public_evidence({"inputs": {**expected,
            "generation_origin": {"channel_uuid": "channel-a", "shot_uuid": "shot-a", "number": 1,
                                  "name": "Original Dinoster shot"}}})
        self.assertEqual({key: evidence[key] for key in expected}, expected)
        self.assertEqual(evidence["shot"]["name"], "Original Dinoster shot")

    def test_connected_historical_imageasset_and_hidden_only_value_do_not_reclassify_shot(self):
        node = Node(); node.select("dinoster5"); node.shot()
        graph = Graph(node); graph.direct(project="dinoster5")
        before = deepcopy(node.parameter_values)
        with graph.context():
            selected = node._capture_imageasset_project_selection()
        self.assertEqual(selected["schema"], t.PROJECT_SELECTION_SCHEMA)
        self.assertEqual(selected["project"], {"project_id": "dinoster5", "project_name": "다이노스터"})
        self.assertEqual(node.parameter_values, before)
        self.assertEqual(node.transport.calls, [])
        self.assertEqual(node.bridge.posts, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
