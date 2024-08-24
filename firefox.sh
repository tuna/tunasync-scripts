#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://packages.mozilla.org/"}"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"

# =================== APT repos ===============================
# see: https://packages.mozilla.org/apt/dists/mozilla/InRelease
"$apt_sync" --delete "${BASE_URL/}/apt" mozilla main amd64,i386,arm64 "${APT_PATH}"
echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
