#!/usr/bin/env bash
# Run inside Git Bash on Windows x64 in the build directory described in README.txt.
set -euo pipefail
base=$(pwd)
export LC_ALL=C
export SOURCE_DATE_EPOCH=1735689600
export PATH="$base:/usr/bin:$base/w64devkit/bin:$PATH"
prefix="$(cygpath -m "$base/prefix")"
export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="$PKG_CONFIG_PATH"
mkdir -p "$prefix"
cd "$base/x264-31e19f92f00c7003fa115047ce50978bc98c3a0d"
bash ./configure --prefix="$prefix" --host=x86_64-w64-mingw32 --enable-static --disable-cli \
  --disable-avs --disable-opencl --disable-lavf --disable-ffms --disable-gpac --disable-lsmash
make -j"${HMB_BUILD_JOBS:-12}" install-lib-static
cd "$base/ffmpeg-7.1.5"
# Windows limits the command line length. GNU ar accepts the same object list
# from a response file. Apply only this build-rule change to the extracted tree.
sed -i 's/$(AR_O) \$\^$/$(AR_O) $(file >$@.inputs,$^)@$@.inputs/' ffbuild/library.mak
sh ./configure --prefix=/usr/local --target-os=mingw32 --arch=x86_64 \
  --cc=gcc --pkg-config=pkg-config --pkg-config-flags=--static --extra-ldflags=-static \
  --disable-autodetect --disable-debug --disable-doc --disable-network --disable-shared --enable-static \
  --disable-everything --disable-programs --enable-ffmpeg --enable-ffprobe --enable-gpl --enable-libx264 \
  --enable-decoder='h264,hevc,prores,dnxhd,mjpeg,mpeg4,mpeg2video,vp8,vp9,av1,qtrle,rawvideo,ffv1,aac,alac,ac3,eac3,mp3,opus,pcm_*' \
  --enable-encoder=libx264,aac,mjpeg --enable-parser=h264,hevc,mjpeg,mpeg4video,mpegaudio,aac,ac3 \
  --enable-demuxer=mov,matroska,m4v --enable-muxer=mp4,image2pipe --enable-protocol=file,pipe \
  --enable-bsf=setts,aac_adtstoasc,h264_mp4toannexb,hevc_mp4toannexb,extract_extradata \
  --enable-filter=scale,format,pad,tpad,trim,setsar,aresample,aformat,anull,null,transpose,hflip,vflip,crop,setpts,atrim
make V=1 -j"${HMB_BUILD_JOBS:-12}" ffmpeg.exe ffprobe.exe
strip ffmpeg.exe ffprobe.exe
