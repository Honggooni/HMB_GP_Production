# Third-party notices

HMB's private Agent implementation includes reviewed parts of Griptape Nodes
Library Standard under Apache-2.0 (library 0.91.1, Python project 0.86.0,
commit `29e91f362343e2eba4fb3d2d48ef05d43bb34d53`). The source and modified
file hashes are in `_hmb_native_agent/UPSTREAM.json`. The original Apache
license accompanies those files in `_hmb_native_agent/LICENSE`. HMB relocated
the Python modules, preserved the Agent wire format and deferred loading the
DateTime tool dependency. The optional Python tool and provider distributions
retain their own license files in the local installation.

HMB GP Production declares the following direct editor/runtime dependencies:

- Pillow >=12.3.0,<14 — MIT-CMU license. This is a declared compatibility
  range, not a bundled Pillow distribution. A compatible host-installed
  version is reused, including the current engine's Pillow 13.
- imageio-ffmpeg 0.6.0 — BSD-2-Clause license
- HTTPX 0.28.1 — BSD-3-Clause license
- The FFmpeg executable supplied through imageio-ffmpeg is governed by the
  license and build configuration published with that binary.

Windows review media generation uses the packaged FFmpeg 7.1.5 utilities and
the statically linked VideoLAN x264 library. These separate executables are
licensed under GPL-2.0-or-later. The corresponding upstream source archives,
build instructions, license and MinGW runtime notices accompany the utilities
under `resources/media-tools/`. See [FFmpeg](https://ffmpeg.org/) and
[VideoLAN x264](https://www.videolan.org/developers/x264.html).

Legacy TOS installations may contain a separate `.venv-tos` interpreter:

- Volcengine TOS Python SDK 2.9.2 — Apache-2.0 license
- Its dependencies, including wrapt 1.16.0, belong only to that isolated
  interpreter. They are not imported into the Griptape engine environment.
- After a normal Git Update/Override, the next cold library load safely
  migrates known legacy TOS editor dependencies with a verified recovery copy.
  Loaded dependencies defer migration until Griptape is restarted.
  Generator render inputs use Griptape Cloud.
- The included installer is an alternative for explicit installation and recovery.
  On a fresh installation, `-PrepareTosRuntime` provisions this optional runtime.
  Rendering does not install packages.

Griptape Nodes, Griptape Standard Library, Autodesk Maya, Volcengine Ark,
Volcengine TOS, and Seedance are separate products or services governed by their
own terms, pricing, model-access, content, and retention policies. This notice
does not replace their complete license texts. Release recipients should retain
the package metadata and notices delivered with those components.
