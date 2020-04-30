#!/bin/bash
# requires: createrepo reposync wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://repos.influxdata.com"}

YUM_PATH="${BASE_PATH}/yum"
UBUNTU_PATH="${BASE_PATH}/ubuntu"
DEBIAN_PATH="${BASE_PATH}/debian"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

wget -O ${BASE_PATH}/influxdb.key ${BASE_URL}/influxdb.key

# =================== APT repos ===============================

"$apt_sync" --delete "${BASE_URL}/ubuntu" @ubuntu-lts stable amd64,i386,armhf,arm64 "$UBUNTU_PATH"
echo "Ubuntu finished"
"$apt_sync" --delete "${BASE_URL}/debian" @debian-current stable amd64,i386,armhf,arm64 "$DEBIAN_PATH"
echo "Debian finished"


# =================== YUM/DNF repos ==========================
"$yum_sync" "${BASE_URL}/rhel/@{os_ver}/@{arch}/stable/" 6-8 influxdata x86_64 "el@{os_ver}-@{arch}" "$YUM_PATH"
echo "YUM finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
