# Modified by HMB: use the private, release-pinned Agent namespace.
"""Nodes package."""

# The verified Local installer supplies optional provider/tool dependencies here.
# This directory contains only distributions missing from the approved engine.
# Prefer it to other libraries' edit environments without executing .pth files.
from pathlib import Path
from importlib import metadata
import sys

_local_dependencies = Path(__file__).resolve().parent.parent / ".hmb-agent-deps"
if _local_dependencies.is_dir() and str(_local_dependencies) not in sys.path:
    ahead = next((index for index, path in enumerate(sys.path)
                  if ".venv" in Path(path).parts), len(sys.path))
    sys.path.insert(ahead, str(_local_dependencies))


def check_tool_dependency(module_name, distribution):
    """Keep the engine's live modules; reject an incompatible preloaded tool locally."""
    module = sys.modules.get(module_name)
    origin = getattr(module, "__file__", None)
    if not origin or not _local_dependencies.is_dir():
        return
    file = Path(origin).resolve()
    if file.is_relative_to(_local_dependencies):
        return
    candidates = list(metadata.Distribution.discover(name=distribution, path=[str(_local_dependencies)]))
    if not candidates:
        return
    site = next((p for p in file.parents if p.name.casefold() in ("site-packages", "dist-packages")), None)
    existing = list(metadata.Distribution.discover(name=distribution, path=[str(site)])) if site else []
    if len(existing) != 1 or existing[0].version != candidates[0].version:
        raise RuntimeError(f"HMB Agent requires {distribution} {candidates[0].version}. "
                           "A different copy is already loaded. Restart the HMB host before using this tool.")
