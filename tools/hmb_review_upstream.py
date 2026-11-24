"""Compare downloaded official release indexes with the HMB-reviewed baseline."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DESKTOP = "0.31.0"
STANDARD = "0.91.1"
DESKTOP_SHA256 = "26939b3fa70cf9d355c05b2a86594177e5df6949aa7c5ec2c6f24794f0c748e3"


def version_parts(value: str) -> tuple[int, ...] | None:
    if re.fullmatch(r"\d+\.\d+\.\d+", value):
        return tuple(map(int, value.split(".")))
    return None


def pending(rows, baseline, component):
    minimum = version_parts(baseline)
    assert minimum is not None
    selected = []
    for version, notes, rebuilt in rows:
        parts = version_parts(version)
        if parts is None or parts < minimum or (parts == minimum and not rebuilt):
            continue
        selected.append((parts, {"component": component, "version": version,
                                 "reissued": rebuilt, "official_notes": notes.strip()}))
    return [row for _, row in sorted(selected, key=lambda entry: entry[0])]


def review(desktop_index, standard_index):
    desktop = []
    for row in desktop_index["Assets"]:
        if (row["Type"] != "Full" or row["PackageId"] != "ai.griptape.nodes.desktop"
                or not row["FileName"].endswith("-win-x64-stable-full.nupkg")):
            continue
        reissued = row["Version"] == DESKTOP and row["SHA256"].lower() != DESKTOP_SHA256
        desktop.append((row["Version"], row.get("NotesMarkdown") or "", reissued))
    standard = [(row["tag_name"].removeprefix("v"), row.get("body") or "", False)
                for row in standard_index if not row.get("draft") and not row.get("prerelease")]
    if not desktop or not any(version_parts(ver) for ver, _, _ in standard):
        raise ValueError("The input must include official stable Windows packages and Standard releases.")
    return {"baseline": {"desktop": DESKTOP, "standard_stable": STANDARD},
            "candidates": pending(desktop, DESKTOP, "Desktop") + pending(standard, STANDARD, "Standard")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop-feed", type=Path, required=True)
    parser.add_argument("--standard-releases", type=Path, required=True)
    args = parser.parse_args()
    report = review(json.loads(args.desktop_feed.read_bytes()),
                    json.loads(args.standard_releases.read_bytes()))
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
