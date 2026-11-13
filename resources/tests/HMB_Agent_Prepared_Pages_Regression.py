"""Public shot pages preserve durable state and cannot expose runtime prompts."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).parent)]
from HMB_Agent_Page_View_Cache_Regression import view_fixture, module
import HMB_Analysis_Node_Regression as analysis_fixture
analysis = analysis_fixture.analysis


class PreparedPages(unittest.TestCase):
    def test_agent_rows_use_public_projection_not_saved_runtime_prompt(self):
        node, owner, _, rows, _, _, setter = view_fixture()
        node._hmb_prompt_display_owner = lambda: owner
        node._hmb_shot_slots['channel\x1fshot-2'] = {'values': {
            'prompt': 'PRIVATE RUNTIME MUST NOT LEAK', 'additional_context': 'Authored context'},
            'outputs': {'output': 'Saved result'}}
        before = copy.deepcopy(node._hmb_shot_slots)
        with patch.object(module._BaseAgent, 'set_parameter_value', setter):
            node._hmb_layout_shot_editor()
        page = node.parameter_values[module._AGENT_SHOT_ROW_PREFIX+'2']['display_page']
        self.assertEqual(page, {'prompt': 'Prepared shot-2 literal {braces} OFF 0',
                               'additional_context': 'Authored context', 'output': 'Saved result'})
        self.assertEqual(node._hmb_shot_slots, before)
        owner._hmb_prompt_shot_document.assert_not_called()

    def test_analysis_pages_are_uuid_scoped_public_and_not_durable(self):
        node = analysis_fixture.AnalysisNodeRegression.make_node()
        node._active = ('channel', 'shot-1')
        node._catalog = {'shots': [{'number': n, 'shot_uuid': f'shot-{n}', 'name': f'Shot {n}'} for n in range(1, 6)]}
        node._sources_key = node._active
        node._default_model = None
        node._ack = node._status = node._error = ''
        node._role_options = lambda: ('before', ['before','after'], False)
        for n in range(1, 6):
            slot = analysis._default_slot()
            slot.update(guidance=f'Guide {n}', path='PRIVATE PATH', field_overrides={'PROJECT_STYLE_LOOK': f'Edited {n}'})
            node._slots[analysis._scope('channel',f'shot-{n}')] = slot
        before = copy.deepcopy(node._slots)
        published = {}
        with patch.object(analysis, '_set_parameter_silently', side_effect=lambda _,key,value: published.update({key:value})):
            analysis.HMBAnalysisAgent._publish(node)
        pages = published[analysis.UI]['display_pages']
        self.assertEqual(set(pages), {f'shot-{n}' for n in range(1,6)})
        for n in range(1,6):
            self.assertEqual(pages[f'shot-{n}']['slot']['guidance'],f'Guide {n}')
            self.assertNotIn('path',pages[f'shot-{n}']['slot'])
        self.assertNotIn('display_pages',published[analysis.STATE])
        self.assertEqual(published[analysis.STATE]['slots'],before)
        self.assertEqual(node._slots,before)


if __name__ == '__main__':
    unittest.main()
