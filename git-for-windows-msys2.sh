#!/bin/bash
# Run in Docker image: tunathu/git-for-windows-msys2
set -e
set -o pipefail

_here=`dirname $(realpath $0)`

BASE_PATH="${TUNASYNC_WORKING_DIR}"

mkdir -p $BASE_PATH/x86-64/
mkdir -p $BASE_PATH/i686/
azcopy sync --recursive https://wingit.blob.core.windows.net/x86-64/ $BASE_PATH/x86-64/
azcopy sync --recursive https://wingit.blob.core.windows.net/i686/ $BASE_PATH/i686/
echo "finished"
