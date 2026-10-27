"""Portable regression for native Agent adapter arguments, no SDK/provider import.

The current Standard Agent supplies state, prompt and output_type. Team v0.8.01
accepted only state and prompt, turning argument binding into HOST_ADAPTER.
Execute the actual product methods with local native-boundary sentinels so
legacy calls and all extra native arguments remain intact. Actual installed
Standard/PydanticAI serialization has a separate installed-SDK regression.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import inspect
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get('HMB_AGENT_ADAPTER_SOURCE', ROOT / 'HMBAgentLibrary.py'))
TREE = ast.parse(SOURCE.read_bytes(), filename=str(SOURCE))


def method(name):
    return deepcopy(next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == name))


CALLS = []
RESULT = object()


class NativeBoundary:
    def _process(self, *args):
        CALLS.append(args)
        return RESULT


GLOBALS = {
    '__name__': __name__, 'Any': object, 'hashlib': hashlib, 'json': __import__('json'),
    '_HMBWebRerenderExecution': type('WebExecution', (), {}),
    '_VERIFIED_PROMPT_SOURCE_ATTRIBUTE': '_verified_source',
    '_with_english_agent_output_contract': lambda prompt: prompt,
    '_prompt_text_sha256': lambda text: hashlib.sha256(text.encode('utf-8')).hexdigest(),
    'NativeBoundary': NativeBoundary,
}
FUNCTIONS = [method('_run_native_with_literal_hmb_input'), method('_hmb_native_failure_code')]
MODEL_SELECTION_ERROR = deepcopy(next(
    n for n in TREE.body
    if isinstance(n, ast.ClassDef) and n.name == '_HMBModelSelectionRequired'
))
CLASS = ast.ClassDef(name='ProductAdapter', bases=[ast.Name(id='NativeBoundary', ctx=ast.Load())],
                     keywords=[], body=[method('_process')], decorator_list=[])
compiled = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
                           MODEL_SELECTION_ERROR, *FUNCTIONS, CLASS], type_ignores=[])
exec(compile(ast.fix_missing_locations(compiled), str(SOURCE), 'exec'), GLOBALS)
Adapter = GLOBALS['ProductAdapter']
literal_run = GLOBALS['_run_native_with_literal_hmb_input']
classify = GLOBALS['_hmb_native_failure_code']


class BaseArtifact:
    pass


class TextArtifact(BaseArtifact):
    def __init__(self, value):
        self.value = value


class PromptTask:
    def _process_task_input(self, value):
        return ('native-template', value)


class Listener:
    def __init__(self, callback, **kwargs):
        self.callback = callback
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None


def task_modules():
    package = ModuleType('griptape')
    artifacts = ModuleType('griptape.artifacts')
    artifacts.BaseArtifact, artifacts.TextArtifact = BaseArtifact, TextArtifact
    events = ModuleType('griptape.events')
    events.EventListener = Listener
    events.StartStructureRunEvent = type('Start', (), {})
    events.FinishStructureRunEvent = type('Finish', (), {})
    tasks = ModuleType('griptape.tasks')
    tasks.PromptTask = PromptTask
    return {'griptape': package, 'griptape.artifacts': artifacts,
            'griptape.events': events, 'griptape.tasks': tasks}


class NativeAdapterArity(unittest.TestCase):
    def setUp(self):
        CALLS.clear()
        self.node = Adapter()
        self.node._hmb_rules_active = False
        self.node._hmb_lifecycle_generation = 1
        self.node._hmb_lifecycle_is_live = lambda generation: generation == 1
        self.node._hmb_revalidate_prompt_manager_owner = lambda: None
        self.node.is_cancellation_requested = False
        self.node._hmb_runtime_prompt = 'Verified source remains caller-owned.'
        self.state = SimpleNamespace(model='native-state')
        self.prompt = 'Literal {{SIGN}} {% raw %} 한글 @image1 @video1'
        self.output_type = {'properties': {'instruction': {'type': 'string'}}, 'required': ['instruction']}

    def assert_forwarded(self, active, extras):
        self.node._hmb_rules_active = active
        original = deepcopy(self.output_type)
        with patch.dict(sys.modules, task_modules()):
            actual = self.node._process(self.state, self.prompt, *extras)
        self.assertIs(actual, RESULT)
        self.assertEqual(len(CALLS), 1)
        self.assertEqual(len(CALLS[0]), 2 + len(extras))
        self.assertIs(CALLS[0][0], self.state)
        self.assertIs(CALLS[0][1], self.prompt)
        for actual_arg, expected in zip(CALLS[0][2:], extras):
            self.assertIs(actual_arg, expected)
        self.assertEqual(self.output_type, original)

    def test_legacy_two_native_arguments_still_work(self):
        self.assert_forwarded(False, ())

    def test_current_standard_output_type_forwards_unchanged(self):
        self.assert_forwarded(False, (self.output_type,))

    def test_current_hmb_output_type_forwards_through_literal_helper(self):
        self.assert_forwarded(True, (self.output_type,))

    def test_all_extra_native_arguments_preserve_identity_and_false_zero(self):
        self.assert_forwarded(True, (self.output_type, 0, False, None))

    def test_task_literal_hook_forwards_arguments_and_restores_native_input(self):
        task = PromptTask()
        agent = SimpleNamespace(id='offline-task-owner', tasks=[task])
        other_input = object()
        calls = []
        def native(structure, prompt, *extras):
            calls.append((structure, prompt, extras))
            processed = task._process_task_input(prompt)
            self.assertIsInstance(processed, TextArtifact)
            self.assertIs(processed.value, self.prompt)
            self.assertEqual(task._process_task_input(other_input), ('native-template', other_input))
            return RESULT
        with patch.dict(sys.modules, task_modules()):
            self.assertIs(literal_run(native, agent, self.prompt, self.output_type, 0, False), RESULT)
        self.assertIs(calls[0][0], agent)
        self.assertIs(calls[0][1], self.prompt)
        self.assertIs(calls[0][2][0], self.output_type)
        self.assertEqual(calls[0][2][1:], (0, False))
        self.assertNotIn('_process_task_input', task.__dict__)

    def test_literal_task_hook_is_restored_when_native_boundary_raises(self):
        task = PromptTask()
        def native(*args):
            raise TypeError('offline-native-error')
        with patch.dict(sys.modules, task_modules()):
            with self.assertRaisesRegex(TypeError, 'offline-native-error'):
                literal_run(native, SimpleNamespace(id='owner', tasks=[task]), self.prompt, self.output_type)
        self.assertNotIn('_process_task_input', task.__dict__)

    def test_old_adapter_signature_reproduces_host_adapter_before_native_work(self):
        class OldAdapter:
            def _process(self, state, prompt):
                self.fail('The three-argument Standard call cannot enter this body.')
        legacy = OldAdapter()
        callback = lambda: legacy._process(self.state, self.prompt, self.output_type)
        with self.assertRaises(TypeError) as failure:
            callback()
        self.assertEqual(classify(failure.exception), 'HOST_ADAPTER')
        inspect.signature(Adapter._process).bind(self.node, self.state, self.prompt, self.output_type)

    def test_saved_unsupported_model_requires_selection_without_host_adapter_fallback(self):
        error = GLOBALS['_HMBModelSelectionRequired']('Saved model is unavailable.')
        self.assertEqual(classify(error), 'MODEL_SELECTION_REQUIRED')


if __name__ == '__main__':
    unittest.main(verbosity=2)
