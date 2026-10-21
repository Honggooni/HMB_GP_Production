"""Portable CI entry for actual Broker auth methods and pure reference leases.

The installed SDK lifecycle remains a separate manual test. No Standard/SDK,
credential store, network, provider or real storage client is imported here.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

path = Path(__file__).with_name("HMB_Seedance_Reference_Lease_Regression.py")
spec = importlib.util.spec_from_file_location("portable_reference_auth_contract", path)
assert spec and spec.loader
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case)
    for case in (fixture.LeaseTests, fixture.AuthContinuityTests))
assert suite.countTestCases() == 15
result = unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({"status": "PASS" if result.wasSuccessful() else "FAIL", "tests": result.testsRun,
    "actual_broker_method_bodies": True, "synthetic_loader_and_opener": True,
    "sdk_imported": "griptape_nodes" in sys.modules, "credentials_read": 0,
    "network_calls": 0, "paid_renders": 0}))
raise SystemExit(0 if result.wasSuccessful() else 1)
