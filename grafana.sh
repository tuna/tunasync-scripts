#!/bin/bash
# requires: createrepo reposync wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packages.grafana.com/oss"}

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

# =================== APT repos ===============================
"$apt_sync" --delete "${BASE_URL}/deb" stable,beta main amd64,armhf,arm64 "$APT_PATH"
echo "APT finished"


# =================== YUM/DNF repos ==========================
"$yum_sync" "${BASE_URL}/@{comp}" 7 rpm,rpm-beta x86_64 "@{comp}" "$YUM_PATH"
echo "YUM finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE; rm $REPO_SIZE_FILE
