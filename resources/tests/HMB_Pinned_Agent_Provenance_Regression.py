"""Check approved pinned host provenance independently of policy contents."""
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _hmb_common as common


class DesktopProvenance(unittest.TestCase):
    def test_approved_private_distribution_and_stock_reject_untrusted_hosts(self):
        with TemporaryDirectory() as temp, ExitStack() as stack:
            local = Path(temp).resolve()
            vendor = local / "ai.griptape.nodes.desktop"
            host = vendor / "HMB-pinned-desktop-0.31.0-74bc17db-b79908fc"
            python = host / common._AGENT_POLICY_DESKTOP_PYTHON
            parent = host / common._AGENT_POLICY_DESKTOP_EXE
            files = {}
            for relative in common._AGENT_POLICY_PINNED_HOST_FILES:
                path = host / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                content = str(relative).encode()
                path.write_bytes(content)
                files[relative] = sha256(content).hexdigest()
            stack.enter_context(patch.object(common, "_AGENT_POLICY_PINNED_HOST_FILES", files))
            stack.enter_context(patch.object(common, "_agent_policy_known_folder", return_value=local))
            # Windows-only Win32 measurements are represented as fixture data.
            stack.enter_context(patch.object(common, "os", unittest.mock.Mock(wraps=common.os, name="fixture_os")))
            common.os.name = "nt"
            stack.enter_context(patch.object(sys, "executable", str(python)))
            argv = stack.enter_context(patch.object(common, "_agent_policy_process_command_line",
                                                      return_value=(str(python), "-m", "griptape_nodes_app")))
            parent_api = stack.enter_context(patch.object(common, "_agent_policy_parent_process_image", return_value=str(parent)))
            self.assertTrue(common._agent_policy_process_provenance_valid())
            argv.return_value = (str(python), "-c", "fixture")
            self.assertFalse(common._agent_policy_process_provenance_valid())
            argv.return_value = (str(python), "-m", "griptape_nodes_app")
            parent_api.return_value = str(vendor / "current" / parent.name)
            self.assertFalse(common._agent_policy_process_provenance_valid())
            parent_api.return_value = str(parent)
            with patch.object(common, "_agent_policy_known_folder", return_value=local / "foreign"):
                self.assertFalse(common._agent_policy_process_provenance_valid())
            (host / "resources/app.asar").write_bytes(b"unexpected distribution")
            self.assertFalse(common._agent_policy_process_provenance_valid())
            stock = vendor / "current"
            stock_python = stock / common._AGENT_POLICY_DESKTOP_PYTHON
            with patch.object(sys, "executable", str(stock_python)):
                argv.return_value = (str(stock_python), "-m", "griptape_nodes_app")
                parent_api.return_value = str(stock / parent.name)
                self.assertTrue(common._agent_policy_process_provenance_valid())


if __name__ == "__main__":
    unittest.main()
