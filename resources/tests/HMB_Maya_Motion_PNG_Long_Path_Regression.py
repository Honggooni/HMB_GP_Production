"""Exercise the real Motion Guide PNG writer with Windows MAX_PATH frames."""
from __future__ import annotations

import ast
import io
import ntpath
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import zlib


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"
tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in {"_png_chunk", "_write_motion_guide_png"}]
assert len(functions) == 2
namespace = {"io": io, "os": os, "struct": struct, "zlib": zlib,
             "MOTION_GUIDE_PNG_COMPRESSION_LEVEL": 3}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(RUNNER), "exec"), namespace)
write_png = namespace["_write_motion_guide_png"]
canvas = bytearray([255, 0, 0, 0, 255, 0, 0, 0, 255, 128, 64, 32])


def pixels(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, compressed = 8, bytearray()
    while offset < len(data):
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        crc = struct.unpack(">I", data[offset + 8 + size:offset + 12 + size])[0]
        assert crc == zlib.crc32(kind + payload) & 0xFFFFFFFF
        if kind == b"IHDR":
            assert struct.unpack(">IIBBBBB", payload) == (2, 2, 8, 2, 0, 0, 0)
        if kind == b"IDAT":
            compressed.extend(payload)
        offset += 12 + size
    return zlib.decompress(compressed)


with tempfile.TemporaryDirectory(prefix="hmb-motion-png-") as temporary:
    directory = Path(temporary)
    short = directory / "short.png"
    write_png(str(short), 2, 2, canvas)
    expected = b"\0" + bytes(canvas[:6]) + b"\0" + bytes(canvas[6:])
    assert pixels(short) == expected
    if os.name == "nt":
        # The directory itself stays below MAX_PATH and already exists, as in
        # shared Maya staging. Only the authored frame name crosses the limit.
        while len(str(directory)) < 100:
            directory = directory / "capture-staging"
        directory.mkdir(parents=True)
        for total in (270, 300):
            long = directory / ("x" * (total - len(str(directory)) - 5) + ".png")
            assert len(str(long)) == total and len(long.name) < 256
            write_png(str(long), 2, 2, canvas)
            # The test runtime may itself be Maya's non-long-path-aware Python.
            native = Path("\\\\?\\" + str(long))
            assert pixels(native) == expected
            native.unlink()


# Verify that UNC, already-prefixed paths and ordinary short names retain the
# exact file authority, without accessing a share or depending on network I/O.
class CapturedFile(io.BytesIO):
    def close(self):
        self.written = self.getvalue()
        super().close()


opened = []
def capture_open(path, mode):
    assert mode == "wb"
    handle = CapturedFile()
    opened.append((path, handle))
    return handle


namespace["io"] = SimpleNamespace(open=capture_open)
namespace["os"] = SimpleNamespace(name="nt", path=ntpath)
unc = "\\\\fixture-server\\share\\" + "nested\\" * 40 + "frame.png"
prefixed = "\\\\?\\C:\\" + "nested\\" * 40 + "frame.png"
for value, expected_path in ((unc, "\\\\?\\UNC\\" + unc[2:]),
                             (prefixed, prefixed), ("C:\\short\\frame.png", "C:\\short\\frame.png")):
    write_png(value, 2, 2, canvas)
    assert opened[-1][0] == expected_path
    assert opened[-1][1].written.startswith(b"\x89PNG\r\n\x1a\n")
coverage = "270/300-character Windows writes, " if os.name == "nt" else "portable short-path write, "
print("PASS: Motion Guide PNG " + coverage + "exact pixels/CRC, UNC and existing-prefix preservation")
