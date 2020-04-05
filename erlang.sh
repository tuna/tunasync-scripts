#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL="https://packages.erlang-solutions.com"

YUM_PATH="${BASE_PATH}/centos"
UBUNTU_PATH="${BASE_PATH}/ubuntu"
DEBIAN_PATH="${BASE_PATH}/debian"

# =================== APT repos ===============================
"$apt_sync" "${BASE_URL}/ubuntu" @ubuntu-lts contrib amd64,i386 "$UBUNTU_PATH"
echo "Ubuntu finished"
"$apt_sync" "${BASE_URL}/debian" @debian-current contrib amd64,i386 "$DEBIAN_PATH"
echo "Debian finished"

# =================== YUM repos ===============================
"$yum_sync" "${BASE_URL}/rpm/centos/@{os_ver}/@{arch}" 6-8 erlang x86_64 "@{os_ver}" "$YUM_PATH"
echo "YUM finished"
