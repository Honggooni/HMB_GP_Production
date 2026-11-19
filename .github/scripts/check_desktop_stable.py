"""Check the vendor Stable feed without downloading or installing Desktop."""
import json
import re
from urllib.request import urlopen

FEED = "https://downloads.griptapenodes.com/stable/releases.win-x64-stable.json"
REVIEWED_VERSION = "0.30.3"
REVIEWED_SHA256 = "b41d04bb7a54fe4981254b07f77d9308180428df0fabfb8465637f184d502964"


def check(assets):
    builds = [row for row in assets if row.get("PackageId") == "ai.griptape.nodes.desktop"
              and row.get("Type") == "Full"
              and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", row["Version"])]
    latest = max((row["Version"] for row in builds),
                 key=lambda version: tuple(map(int, version.split("."))), default=None)
    hashes = {row["SHA256"].lower() for row in builds if row["Version"] == latest}
    if latest != REVIEWED_VERSION or hashes != {REVIEWED_SHA256}:
        raise SystemExit(f"Windows Stable {latest} differs from tested Desktop {REVIEWED_VERSION}. "
                         "Run the staged SDK, Editor, saved-workflow and CGT compatibility checks before release.")
    return latest


if __name__ == "__main__":
    with urlopen(FEED, timeout=30) as response:
        print("Verified Windows Desktop Stable", check(json.load(response)["Assets"]))
