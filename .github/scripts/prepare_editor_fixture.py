"""Extract the pinned editor from its wheel and build the integration test overlay."""
from hashlib import sha256
from pathlib import Path
import sys
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from hmb_griptape_update_preflight import REVIEWED_HOSTS, build, inspect_editor_fixtures
from restore_rodong_local_editor import editor_profile


def prepare(wheel: Path, target: Path, version: str, bundle: str) -> None:
    target.mkdir(parents=True, exist_ok=False)
    prefix = "griptape_nodes_editor_dist/editor/"
    with ZipFile(wheel) as archive:
        for member in archive.infolist():
            if member.filename.startswith(prefix) and not member.is_dir():
                dest = (target / member.filename[len(prefix):]).resolve()
                if not dest.is_relative_to(target.resolve()):
                    raise ValueError("Invalid editor wheel member")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.read(member))
    fixtures = next(files for (_, editor), (_, files) in REVIEWED_HOSTS.items() if editor == version)
    inspect_editor_fixtures(target / "assets", fixtures)
    entry = (target / "index-editor.html").read_bytes()
    profile = editor_profile(entry)
    if bundle != profile.bundle or sha256(entry).hexdigest() != profile.entry_digest:
        raise ValueError("Wheel entry and requested bundle disagree")
    candidate = build((target / "assets" / bundle).read_bytes())
    if sha256(candidate).hexdigest() != profile.overlay_digest:
        raise ValueError("Compiled overlay differs from the packaged profile")
    (target / "overlay.js").write_bytes(candidate)


if __name__ == "__main__":
    prepare(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4])
