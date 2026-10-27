"""Actual SDK cold save/reopen and five independent slots; synthetic CGT IDs."""
import os
from pathlib import Path
import runpy
from unittest import mock

if __name__ == '__main__':
    with mock.patch.dict(os.environ, {'HMB_HIERARCHY_TEST_CGT': '1'}):
        runpy.run_path(str(Path(__file__).with_name('HMB_Shot_Hierarchy_Host_Regression.py')), run_name='__main__')
