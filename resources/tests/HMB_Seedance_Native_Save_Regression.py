"""No-network: HMB recovery cannot save/rekey a native Griptape workflow."""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("seedance_stock_save", ROOT / "HMBSeedanceGeneration.py")
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)

def checkpoint(node):
    return deepcopy(node.get_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER))

def reopen(saved):
    node = target.HMBSeedanceGeneration(name="Reopened Generator")
    node.set_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER, deepcopy(saved), initial_setup=True)
    node._restore_generation_recovery_preview()
    return node

async def verify(folder):
    context = SimpleNamespace(name="unsaved:manual-audit", autosave=False)
    file = folder / "manual.py"
    async def manual_save(request):
        context.name = "manual"
        file.write_text("# user manual save\n", encoding="utf-8")
    with mock.patch.object(target.GriptapeNodes, "ahandle_request", side_effect=manual_save, create=True) as host:
        nodes = [target.HMBSeedanceGeneration(name=f"Generator {i}") for i in range(5)]
        saved = [checkpoint(n) for n in nodes]
        assert len({cp["journal_id"] for cp in saved}) == 5
        for i, n in enumerate(nodes):
            n._set_generation_recovery_checkpoint(stage="pre_submit", task_id=f"hmb-stock-{i}", task_identity="client_request", status="submitting")
        assert await asyncio.gather(*(n._force_save_generation_recovery_checkpoint(required=True, reason="pre_submit") for n in nodes)) == [True] * 5
        host.assert_not_called()
        assert context.name == "unsaved:manual-audit" and not file.exists()
        assert context.autosave is False
        await host(SimpleNamespace(action="user_save"))
        before = (file.read_bytes(), file.stat().st_mtime_ns)
        for i, n in enumerate(nodes):
            n._set_generation_recovery_checkpoint(stage="accepted", task_id=f"job-accepted-{i}", task_identity="broker_task", status="running")
        await asyncio.gather(*(n._force_save_generation_recovery_checkpoint(required=False, reason="accepted") for n in nodes))
        assert host.call_count == 1 and context.name == "manual" and context.autosave is False
        assert (file.read_bytes(), file.stat().st_mtime_ns) == before
        for i, cp in enumerate(saved):
            restored = reopen(cp)
            assert restored._authoritative_existing_generation_id() == f"job-accepted-{i}"
            assert restored._generation_recovery_blocks_new_submission()
        n = nodes[0]
        n._set_generation_recovery_checkpoint(stage="local_succeeded", task_id="job-accepted-0", task_identity="broker_task", status="succeeded", terminal=True)
        assert await n._force_save_generation_recovery_checkpoint(required=False, reason="local_succeeded")
        assert not reopen(saved[0])._generation_recovery_blocks_new_submission()
        n._clear_generation_recovery_checkpoint()
        assert await n._force_save_generation_recovery_checkpoint(required=False, reason="discard")
        restored = reopen(saved[0])
        restored.parameter_output_values["generation_id"] = "job-stale-output"
        assert restored._generation_recovery_state()["task_id"] == ""
        assert not restored._generation_recovery_blocks_new_submission()
        fresh = target.HMBSeedanceGeneration(name=n.name)
        assert fresh._generation_recovery_state()["task_id"] == ""
        assert checkpoint(fresh)["journal_id"] != saved[0]["journal_id"]
        cp = checkpoint(nodes[1])
        cp.update(prompt="private", credential="secret", media="https://private")
        target._write_seedance_recovery_journal(cp)
        path = target._seedance_recovery_journal_path(cp["journal_id"])
        raw = path.read_text(encoding="utf-8")
        assert all(key not in json.loads(raw) for key in ("prompt", "credential", "media"))
        with mock.patch.object(target.os, "replace", side_effect=OSError("disk error")):
            try:
                await nodes[1]._force_save_generation_recovery_checkpoint(required=True, reason="failure")
            except RuntimeError as exc:
                assert "No render was submitted" in str(exc)
            else:
                raise AssertionError("Journal failure cannot allow billable POST")
            assert not await nodes[1]._force_save_generation_recovery_checkpoint(required=False, reason="failure")
        assert path.read_text(encoding="utf-8") == raw and not list(folder.glob("*.tmp"))
        assert (file.read_bytes(), file.stat().st_mtime_ns) == before and host.call_count == 1
        for invalid in ("{corrupt", json.dumps(checkpoint(nodes[2]))):
            path.write_text(invalid, encoding="utf-8")
            assert reopen(saved[1])._generation_recovery_state()["task_id"] == ""
        await host(SimpleNamespace(action="user_save"))
        assert host.call_count == 2 and context.name == "manual"

with tempfile.TemporaryDirectory(prefix="hmb-stock-save-") as root:
    folder = Path(root)
    assert "generation-recovery" in str(target._seedance_recovery_journal_path("12345678-1234-4234-8234-123456789abc"))
    for invalid in ("../bad", "", "C:/arbitrary"):
        try:
            target._seedance_recovery_journal_path(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid journal identity accepted")
    with mock.patch.object(target, "_seedance_recovery_journal_path", side_effect=lambda key: folder / f"{key}.json"):
        asyncio.run(verify(folder))
source = (ROOT / "HMBSeedanceGeneration.py").read_text(encoding="utf-8")
assert "SaveWorkflowRequest" not in source and "SetWorkflowContextRequest" not in source
print("HMB native save: PASS (5 nodes, zero host saves, reopen, rerender, clear, isolation, atomic failure)")
