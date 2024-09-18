#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://deb.xanmod.org/"}"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

APT_PATH="${BASE_PATH}"

# =================== APT repos ===============================
# see: https://deb.xanmod.org/dists/releases/InRelease
"$apt_sync" --delete "${BASE_URL/}" releases main amd64,i386 "${APT_PATH}"
echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
