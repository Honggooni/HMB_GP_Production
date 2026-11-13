"""Repeated Maya references can retain UUIDs without sharing a DAG object."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'maya/HMB_Maya_Background_Preview.py'

class FakeCmds:
    def __init__(self, paths):
        self.paths = paths

    def ls(self, path, **kwargs):
        if kwargs.get('uuid'):
            return ['shared-reference-file-uuid']
        assert kwargs.get('long') and kwargs.get('allPaths')
        return self.paths.get(path, [])

def load_identity(paths):
    tree = ast.parse(SOURCE.read_text('utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_dag_object_identity')
    namespace = {'cmds': FakeCmds(paths), '_clean': lambda x: str(x or '').strip()}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace['_dag_object_identity']

class ReferenceIdentityRegression(unittest.TestCase):
    def test_independent_references_with_same_uuid_are_distinct(self):
        a='|FireflyAa:ROOT|FireflyAa:BodyShape'
        b='|FireflyAa1:ROOT|FireflyAa1:BodyShape'
        identity=load_identity({a:[a],b:[b]})
        self.assertNotEqual(identity(a),identity(b))

    def test_real_instanced_shape_keeps_same_identity(self):
        a='|FireflyAa|Body|BodyShape';b='|FireflyAa1|Body|BodyShape'
        identity=load_identity({a:[a,b],b:[b,a]})
        self.assertEqual(identity(a),identity(b))

    def test_missing_exact_path_does_not_fall_back(self):
        with self.assertRaisesRegex(RuntimeError,'no longer available'):
            load_identity({})('|FireflyAa2|BodyShape')

if __name__=='__main__':unittest.main()
