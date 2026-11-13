"""READ restores the exact repeated reference, never a UUID-sharing sibling."""
import copy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import HMBVideoPickerLibrary as picker

nodes = [dict(name=name, full_path='|CHARACTERS|' + name, maya_uuid='shared')
         for name in ('FireflyAa', 'FireflyAa1', 'FireflyAa2')]
bindings = [dict(full_dag_path=row['full_path'], maya_uuid='shared', color=color)
            for row, color in zip(nodes, ('Red', 'Blue', 'Green'))]
assignments = [dict(video_slot=1, bindings=bindings)]
before = copy.deepcopy(assignments)
for row, binding in zip(nodes, bindings):
    selected = picker._outliner_selection_after_read(nodes, assignments, 1, row['full_path'], 'shared')
    assert selected['path'] == row['full_path'] and selected['color'] == binding['color'], selected
assert picker._outliner_selection_after_read(nodes, assignments, 1, '|removed', 'shared')['path'] == ''
assert picker._outliner_selection_after_read(nodes, assignments[:0], 1, nodes[1]['full_path'], 'shared')['color'] == ''
single = [dict(name='Renamed', full_path='|Renamed', maya_uuid='unique')]
legacy = [dict(video_slot=1, bindings=[dict(full_dag_path='|Previous', maya_uuid='unique', color='Green')])]
assert picker._outliner_selection_after_read(single, legacy, 1, '|Previous', 'unique')['color'] == 'Green'
ambiguous = [dict(video_slot=1, bindings=[dict(b, maya_uuid='unique') for b in bindings])]
assert picker._outliner_selection_after_read(single, ambiguous, 1, '|Previous', 'unique')['color'] == ''
assert assignments == before
print('READ reference selection: PASS (exact paths, per-reference colors, ambiguity, unique rename, immutable bindings)')
