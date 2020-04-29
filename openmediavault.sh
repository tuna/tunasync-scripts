#!/bin/bash
# requires: wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packages.openmediavault.org/public"}
DISTS=arrakis-proposed,arrakis,erasmus-proposed,erasmus,fedaykin-proposed,fedaykin,ix-proposed,ix,kralizec-proposed,kralizec,omnius-proposed,omnius,sardaukar-proposed,sardaukar,stoneburner-proposed,stoneburner,usul-proposed,usul
APT_PATH="${BASE_PATH}/public"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

# =================== APT repos ===============================
"$apt_sync" --delete "${BASE_URL}" "$DISTS" main,partner amd64,i386,arm64,armel,armhf "$APT_PATH"
echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE; rm $REPO_SIZE_FILE
