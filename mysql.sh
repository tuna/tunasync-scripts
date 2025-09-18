#!/bin/bash
# requires: createrepo reposync wget curl rsync
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://repo.mysql.com"}"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"
UBUNTU_PATH="${APT_PATH}/ubuntu"
DEBIAN_PATH="${APT_PATH}/debian"

# =================== APT repos ===============================
MYSQL_APT_REPOS="mysql-tools,mysql-8.0,mysql-8.4-lts"
"$apt_sync" --delete "${BASE_URL}/apt/ubuntu" @ubuntu-lts $MYSQL_APT_REPOS amd64,i386 "${UBUNTU_PATH}"
echo "Ubuntu finished"
"$apt_sync" --delete "${BASE_URL}/apt/debian" @debian-current $MYSQL_APT_REPOS amd64,i386 "${DEBIAN_PATH}"
echo "Debian finished"

# =================== YUM/DNF repos ==========================
COMPONENTS="mysql-connectors-community,mysql-tools-community,mysql-8.0-community,mysql-8.4-community"
"$yum_sync" "${BASE_URL}/yum/@{comp}/el/@{os_ver}/@{arch}/" @rhel-current "$COMPONENTS" x86_64,aarch64 "@{comp}-el@{os_ver}-@{arch}" "$YUM_PATH"
echo "YUM finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
