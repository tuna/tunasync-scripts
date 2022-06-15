#!/bin/bash
set -e

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

WORKING_DIR="${TUNASYNC_WORKING_DIR}"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

ARCH_LIST="aarch64,arm,i686,x86_64"

"$apt_sync" --delete "$TUNASYNC_UPSTREAM_URL/apt/termux-main"     stable main    $ARCH_LIST "${WORKING_DIR}/termux-packages-24"
"$apt_sync" --delete "$TUNASYNC_UPSTREAM_URL/apt/termux-x11"      x11 main       $ARCH_LIST "${WORKING_DIR}/x11-packages"
"$apt_sync" --delete "$TUNASYNC_UPSTREAM_URL/apt/termux-root"     root stable    $ARCH_LIST "${WORKING_DIR}/termux-root-packages-24"

mkdir -p "${WORKING_DIR}/apt"
ln -fsTr "${WORKING_DIR}/termux-packages-24"         "${WORKING_DIR}/apt/termux-main"
ln -fsTr "${WORKING_DIR}/x11-packages"               "${WORKING_DIR}/apt/termux-x11"
ln -fsTr "${WORKING_DIR}/termux-root-packages-24"    "${WORKING_DIR}/apt/termux-root"
echo "finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
