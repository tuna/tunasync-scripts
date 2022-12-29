#!/bin/bash
# requires: createrepo reposync wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
APT_URL=${TUNASYNC_UPSTREAM_URL:-"https://apt.grafana.com"}
YUM_URL="https://rpm.grafana.com"

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

# =================== APT repos ===============================
"$apt_sync" --delete "${APT_URL}" stable,beta main amd64,armhf,arm64 "$APT_PATH"
echo "APT finished"


# =================== YUM/DNF repos ==========================
"$yum_sync" "${YUM_URL}" 7 rpm x86_64 "@{comp}" "$YUM_PATH"
echo "YUM finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
