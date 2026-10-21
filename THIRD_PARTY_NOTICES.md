# Third-party notices

HMB GP Production declares the following direct editor/runtime dependencies:

- Pillow >=12.3.0,<14 — MIT-CMU license. This is a declared compatibility
  range, not a bundled Pillow distribution. A compatible host-installed
  version is reused, including the current engine's Pillow 13.
- imageio-ffmpeg 0.6.0 — BSD-2-Clause license
- HTTPX 0.28.1 — BSD-3-Clause license
- The FFmpeg executable supplied through imageio-ffmpeg is governed by the
  license and build configuration published with that binary.

Optional Volcengine TOS uploads run in a separate `.venv-tos` interpreter:

- Volcengine TOS Python SDK 2.9.2 — Apache-2.0 license
- Its dependencies, including wrapt 1.16.0, belong only to that isolated
  interpreter. They are not imported into the Griptape engine environment.
- After a normal Git Update/Override, the next cold library load safely
  migrates known legacy TOS editor dependencies with a verified recovery copy.
  Loaded dependencies defer migration until Griptape is restarted. Optional
  TOS preparation runs separately from Cloud generation and saved-result playback.
- The included installer is an alternative for explicit installation and recovery.
  On a fresh installation, `-PrepareTosRuntime` provisions this optional runtime.
  Rendering does not install packages.

Griptape Nodes, Griptape Standard Library, Autodesk Maya, Volcengine Ark,
Volcengine TOS, and Seedance are separate products or services governed by their
own terms, pricing, model-access, content, and retention policies. This notice
does not replace their complete license texts. Release recipients should retain
the package metadata and notices delivered with those components.
