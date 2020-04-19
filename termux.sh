#!/bin/bash
set -e

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

WORKING_DIR="${TUNASYNC_WORKING_DIR}"

ARCH_LIST="aarch64,all,arm,i686,x86_64"

"$apt_sync" --delete-dry-run "https://dl.bintray.com/termux/termux-packages-24"       stable main    $ARCH_LIST "${WORKING_DIR}/termux-packages-24" 
"$apt_sync" --delete-dry-run "https://dl.bintray.com/xeffyr/unstable-packages"        unstable main  $ARCH_LIST "${WORKING_DIR}/unstable-packages" 
"$apt_sync" --delete-dry-run "https://dl.bintray.com/xeffyr/x11-packages"             x11 main       $ARCH_LIST "${WORKING_DIR}/x11-packages" 
"$apt_sync" --delete-dry-run "https://dl.bintray.com/grimler/science-packages-24"     science stable $ARCH_LIST "${WORKING_DIR}/science-packages-24" 
"$apt_sync" --delete-dry-run "https://dl.bintray.com/grimler/game-packages-24"        games stable   $ARCH_LIST "${WORKING_DIR}/game-packages-24" 
"$apt_sync" --delete-dry-run "https://dl.bintray.com/grimler/termux-root-packages-24" root stable    $ARCH_LIST "${WORKING_DIR}/termux-root-packages-24" 

echo "finished"
