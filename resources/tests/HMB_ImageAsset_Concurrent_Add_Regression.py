"""Concurrent Add through the ImageAsset registration entry point, with independent engines."""
from __future__ import annotations

import argparse
from copy import deepcopy
from contextlib import contextmanager
from io import BytesIO
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import mkdtemp, TemporaryDirectory
import time
import traceback
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def png(index):
    from PIL import Image
    data = BytesIO()
    Image.new("RGB", (4, 4), (12 + index, 53, 160)).save(data, "PNG")
    return data.getvalue()


def deselect_connected_import(state, uid):
    """Pass the existing selection through the same toggle as the Shot card."""
    widget = Path(__file__).resolve().parents[2] / "widgets/HMBImageAssetLibraryWidget.js"
    script = """
        import {readFileSync} from 'node:fs';
        const {hmbToggleImageAssetShotAsset} = await import(process.argv[1]);
        const state = JSON.parse(readFileSync(0, 'utf8'));
        const uid = process.argv[2];
        if (!hmbToggleImageAssetShotAsset(state, state.shot_routing.active_shot_uuid, uid)) {
            throw Error('Shot card did not toggle the connected import');
        }
        process.stdout.write(JSON.stringify(state));
    """
    changed = subprocess.run(["node", "--input-type=module", "-e", script, widget.as_uri(), uid],
                             input=json.dumps(state), text=True, encoding="utf-8", capture_output=True, timeout=20)
    assert changed.returncode == 0, changed.stderr
    state = json.loads(changed.stdout)
    row = next(a for a in state["assets"] if a["source_uid"] == uid)
    assert not row["selected"] and row["selection_order"] == 0
    return state


def client(number, connection, workstation, burst_start):
    os.environ["GTN_CONFIG_WORKSPACE_DIRECTORY"] = str(workstation)
    os.environ["HMB_IMAGE_THUMBNAIL_CACHE"] = str(workstation / "thumbs")
    import HMBImageAssetLibrary as lib
    # Exercise registration and file copies without an editor media publishing service.
    lib._asset_thumbnail_url = lambda *_a, **_kw: ""
    try:
        while True:
            case = connection.recv()
            if case is None:
                break
            catalog, external, duplicate = case
            initial = lib._load_project_catalog(catalog, lib._default_state())
            # Native selection sends the enumerated path. Windows may resolve
            # the test parent to UNC while the registered project uses P:.
            assert len(initial["projects"]) == 1
            state = lib._select_catalog_project(initial, initial["projects"][0]["path"])
            anchor = next(row for row in state["assets"] if row["asset_id"] == "Existing")
            anchor.update(selected=True, selection_order=1)
            shot = state["shot_routing"]["shots"][0]
            shot["selected_source_uids"] = [anchor["source_uid"]]
            other = {**deepcopy(shot), "shot_uuid": str(uuid4()), "number": 2, "name": "Other Shot"}
            state["shot_routing"]["shots"].append(other)
            slot = 0 if duplicate else number
            media = {}
            keep_selected = external and number % 2 == 0
            if external:
                source = workstation / "take.png"
                source.write_bytes(png(number))
                state, media = lib._merge_import_input(state, [str(source)])
                item = next(row for row in state["assets"] if row["source_kind"] == "user" and row["import_index"])
                assert state["shot_routing"]["shots"][0]["selected_source_uids"] == [anchor["source_uid"], item["source_uid"]]
                if not keep_selected:
                    state = deselect_connected_import(state, item["source_uid"])
            else:
                item = next(row for row in state["assets"] if row["relative_path"] == f"Images/c{slot}.png")
            expected_before = [anchor["source_uid"], item["source_uid"]] if keep_selected else [anchor["source_uid"]]
            assert [s["selected_source_uids"] for s in state["shot_routing"]["shots"]] == [expected_before, [anchor["source_uid"]]]
            request = {"request_id": f"client-{number}", "project_uid": state["project_uid"],
                       "asset_library_id": item["asset_library_id"], "source_kind": item["source_kind"],
                       "source_uid": item["source_uid"], "relative_path": item["relative_path"],
                       "target_folder": "Images" if external else "", "image_name": f"Image {slot}",
                       "asset_id": f"Asset{slot}", "image_main_type": "Character", "image_sub_type": "Full Appearance"}
            connection.send(("ready", os.getpid()))
            command = connection.recv()
            if command is None:
                break
            if command == "burst":
                if not burst_start.wait(10):
                    raise TimeoutError("Burst barrier was not released")
            elif command != "add":
                raise RuntimeError("Bad test protocol")
            try:
                result = lib._apply_asset_registration(state, request, media)
            except ValueError as exc:
                connection.send(("rejected", str(exc)))
            else:
                assert result["asset_registration_result"]["ok"]
                registered = next(row for row in result["assets"] if row["asset_id"] == f"Asset{slot}" and row["registered"])
                if external:
                    assert registered["import_source_uid"] == item["source_uid"] != registered["source_uid"]
                assert (registered["selected"], registered["selection_order"]) == (keep_selected, 2 if keep_selected else 0)
                expected_after = [anchor["source_uid"], registered["source_uid"]] if keep_selected else [anchor["source_uid"]]
                assert [s["selected_source_uids"] for s in result["shot_routing"]["shots"]] == [expected_after, [anchor["source_uid"]]]
                visible = {row["asset_id"] for row in result["assets"] if row["registered"]}
                assert visible == {"Existing", f"Asset{slot}"}, visible
                connection.send(("committed", f"Asset{slot}"))
    except Exception:
        connection.send(("exception", traceback.format_exc()))
        raise
    finally:
        connection.close()


@contextmanager
def legacy_writer(project):
    """A legacy client holding byte 0 lets all new clients reach the waiting queue."""
    lock_path = project / ".json" / ".hmb_image_assets.lock"
    with lock_path.open("w+b") as handle:
        handle.write(bytes(2))
        handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.lockf(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 0)
        yield


def receive(pipe):
    if not pipe.poll(20):
        raise TimeoutError("Worker did not return")
    result = pipe.recv()
    assert result[0] != "exception", result[1]
    return result


def wait_for_tickets(project, count):
    directory = project / ".json" / ".hmb_image_assets.queue"
    until = time.monotonic() + 5
    while len(list(directory.glob("*.wait"))) != count:
        if time.monotonic() > until:
            raise TimeoutError(f"Expected {count} active writers, got {list(directory.glob('*'))}")
        time.sleep(.005)


def run_case(base, processes, pipes, count, *, external=False, duplicate=False, abandon=False, burst_start=None):
    # Distinct project roots prevent a previous session snapshot from priming this round.
    name = f"{count}-external{int(external)}-duplicate{int(duplicate)}-abandon{int(abandon)}-burst{int(burst_start is not None)}"
    catalog = base / name / "Projects"
    project = catalog / "Show" / "Ai_Ct_image"
    folder = project / "Images"
    folder.mkdir(parents=True)
    metadata = project / ".json"
    metadata.mkdir()
    (folder / "anchor.png").write_bytes(png(6))
    if not external:
        for index in range(1 if duplicate else count):
            (folder / f"c{index}.png").write_bytes(png(index))
    manifest = metadata / "hmb_image_assets.json"
    anchor = {"path": "Images/anchor.png", "image_name": "Existing", "asset_id": "Existing",
              "image_main_type": "Character", "image_sub_type": "Full Appearance"}
    manifest.write_text(json.dumps({"assets": [anchor], "note": "preserve"}), encoding="utf-8")
    for pipe in pipes[:count]:
        pipe.send((catalog, external, duplicate))
    ready = [receive(pipe) for pipe in pipes[:count]]
    assert all(result[0] == "ready" for result in ready) and len({pid for _, pid in ready}) == count
    order = list(reversed(range(count)))
    with legacy_writer(project):
        if burst_start is not None:
            burst_start.clear()
            for index in order:
                pipes[index].send("burst")
            burst_start.set()
            wait_for_tickets(project, count)
        else:
            for waiting, index in enumerate(order, start=1):
                pipes[index].send("add")
                wait_for_tickets(project, waiting)
        assert json.loads(manifest.read_bytes())["assets"] == [anchor]
        if abandon:
            # A real worker process dies while its ticket is first in line.
            processes[order[0]].terminate()
            processes[order[0]].join(5)
            assert not processes[order[0]].is_alive()
    live = order[1:] if abandon else order
    results = {index: receive(pipes[index]) for index in live}
    winners = [index for index in live if results[index][0] == "committed"]
    assert winners == (live[:1] if duplicate else live), results
    if duplicate:
        assert all("already registered" in results[index][1].lower() for index in live[1:]), results
    document = json.loads(manifest.read_bytes())
    records = document["assets"]
    assert document["note"] == "preserve" and records[0] == anchor
    committed = [int(row["asset_id"].removeprefix("Asset")) for row in records[1:]]
    expected = [0 if duplicate else index for index in winners]
    if burst_start is not None:
        assert sorted(committed) == sorted(expected)
    else:
        assert committed == expected
    if external:
        assert len(list(folder.glob("*.png"))) == len(records), "Unregistered import copy remained"
        for row, winner in zip(records[1:], winners, strict=True):
            assert row["import_source_uid"] and (project / row["path"]).read_bytes() == png(winner)
    assert not list((metadata / ".hmb_image_assets.queue").glob("*.wait")), "Waiting ticket leaked"
    assert not list(metadata.glob("*.tmp"))
    return {"clients": count, "source": "external" if external else "project", "duplicate": duplicate,
            "aborted_head": abandon, "simultaneous_barrier": burst_start is not None, "worker_admission_order":
            None if burst_start is not None else order, "committed_asset_numbers": committed,
            "rejected": len(live) - len(winners)}


@contextmanager
def shared_fixture(parent):
    prefix = ".hmb-add-qa-"
    root = Path(parent).resolve(strict=True)
    directory = Path(mkdtemp(prefix=prefix, dir=root))
    def verify():
        resolved = directory.resolve(strict=True)
        if resolved != directory or resolved.parent != root or not resolved.name.startswith(prefix):
            raise ValueError("Unexpected shared test directory")
    verify()
    try:
        yield directory
    finally:
        verify()
        shutil.rmtree(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-test-parent", type=Path, default=os.environ.get("HMB_IMAGEASSET_LOCK_TEST_ROOT"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="hmb-add-five-clients-") as directory, shared_fixture(
            args.shared_test_parent or directory) as base:
        context = multiprocessing.get_context("spawn")
        burst_start = context.Event()
        processes, pipes = [], []
        try:
            for number in range(5):
                home = Path(directory) / f"client-{number}"
                home.mkdir()
                parent, child = context.Pipe()
                process = context.Process(target=client, args=(number, child, home, burst_start))
                process.start()
                child.close()
                processes.append(process)
                pipes.append(parent)
            results = [run_case(base, processes, pipes, n) for n in range(2, 6)]
            results.append(run_case(base, processes, pipes, 5, burst_start=burst_start))
            results.append(run_case(base, processes, pipes, 5, duplicate=True))
            results.append(run_case(base, processes, pipes, 5, external=True))
            results.append(run_case(base, processes, pipes, 5, external=True, duplicate=True))
            results.append(run_case(base, processes, pipes, 5, abandon=True))
            report = json.dumps({"shared_fixture_parent": str(base.parent), "workers": [p.pid for p in processes],
                                 "cases": results}, indent=2)
            if args.report:
                args.report.write_text(report + "\n", encoding="utf-8")
            print(report)
        finally:
            for process, pipe in zip(processes, pipes):
                if process.is_alive():
                    try:
                        pipe.send(None)
                    except (OSError, EOFError):
                        pass
                process.join(3)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                pipe.close()


if __name__ == "__main__":
    main()
