#!/bin/bash
# requires: wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"http://packages.ros.org/ros2"}

APT_PATH="${BASE_PATH}/ubuntu"

# =================== APT repos ===============================
"$apt_sync" --delete "${BASE_URL}/ubuntu" @ubuntu-lts,@debian-current main amd64,armhf,arm64 "$APT_PATH"
echo "APT finished"
