"""Read-only installed Standard/editor compatibility check; exit 1 on drift."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _hmb_image_bash_compat import inspect_standard_compatibility


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standard-root", type=Path)
    parser.add_argument("--editor-root", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--source-only", action="store_true", help="Allow an unavailable editor (reported as unverified)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable diagnostics")
    args = parser.parse_args()
    result = inspect_standard_compatibility(
        args.standard_root, baseline_path=args.baseline, editor_root=args.editor_root,
        require_editor=not args.source_only,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("HMBImageBash: " + result["status"])
        print("Standard: " + str(result["standard"].get("library_version", "unavailable")))
        print("Editor: " + result["editor"]["status"])
        for error in result["errors"]:
            print("- " + error)
    return 0 if result["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
