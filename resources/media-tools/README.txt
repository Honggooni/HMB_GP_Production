HMB Windows x64 review media tools

The ffmpeg.exe and ffprobe.exe in win64 run as separate processes. They read
local MOV/MP4/M4V/WebM sources and produce the JPEG poster and H.264/AAC review MP4.
This build enables only local file and pipe protocols. The configure options
in rebuild-review-tools.sh list its enabled codecs, formats and filters.

This directory contains the complete unmodified corresponding source archives
for FFmpeg and the x264 library statically linked into the executables.
The build is licensed under GPL version 2 or later. See COPYING.GPLv2 and the
copyright and license declarations in each source archive. MINGW-RUNTIME.txt
covers the MinGW runtime. HMB's license for its own code does not apply to
these components. This package is supplied without warranty.

Sources and SHA-256

FFmpeg 7.1.5
https://ffmpeg.org/releases/ffmpeg-7.1.5.tar.xz
de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f

VideoLAN x264 revision 31e19f92f00c7003fa115047ce50978bc98c3a0d
https://code.videolan.org/videolan/x264/-/archive/31e19f92f00c7003fa115047ce50978bc98c3a0d/x264-31e19f92f00c7003fa115047ce50978bc98c3a0d.tar.gz
d053c9d86988d6bc78237ca5205865c5ddf99c98ef4cd9927eec8f6d388f6dd9

Rebuilding on Windows x64

1. In a writable build directory, extract both archives from source/ with
   their top-level directories intact.
2. Extract the w64devkit x64 2.11.0 release there as w64devkit/.
   https://github.com/skeeto/w64devkit/releases/download/v2.11.0/w64devkit-x64-2.11.0.7z.exe
   SHA-256 54c2bb9962e8a30c8270e34c5efc3d5fee579f53087fa7d435b95fbba2af7b2b
   Complete toolchain sources and build instructions are available from the
   same release at https://github.com/skeeto/w64devkit/releases/tag/v2.11.0.
3. Extract nasm.exe from NASM 2.16.03 into the build directory.
   https://www.nasm.us/pub/nasm/releasebuilds/2.16.03/win64/nasm-2.16.03-win64.zip
   SHA-256 3ee4782247bcb874378d02f7eab4e294a84d3d15f3f6ee2de2f47a46aa7226e6
4. From that directory in Git Bash, run bash /path/to/rebuild-review-tools.sh.
   The resulting stripped ffmpeg.exe and ffprobe.exe are in ffmpeg-7.1.5/.
