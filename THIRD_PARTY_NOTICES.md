# Third-party notices

HMB GP Production declares the following direct editor/runtime dependencies:

- Pillow 12.3.0 — MIT-CMU license
- imageio-ffmpeg 0.6.0 — BSD-2-Clause license
- HTTPX 0.28.1 — BSD-3-Clause license
- The FFmpeg executable supplied through imageio-ffmpeg is governed by the
  license and build configuration published with that binary.

Optional Volcengine TOS uploads run in a separate `.venv-tos` interpreter:

- Volcengine TOS Python SDK 2.9.2 — Apache-2.0 license
- Its dependencies, including wrapt 1.16.0, belong only to that isolated
  interpreter. They are not imported into the Griptape engine environment.
- The included installer migrates a previous TOS installation automatically.
  On a new installation, use `-PrepareTosRuntime` to provision this optional
  runtime before selecting TOS uploads. Normal rendering does not install packages.

Griptape Nodes, Griptape Standard Library, Autodesk Maya, Volcengine Ark,
Volcengine TOS, and Seedance are separate products or services governed by their
own terms, pricing, model-access, content, and retention policies. This notice
does not replace their complete license texts. Release recipients should retain
the package metadata and notices delivered with those components.
