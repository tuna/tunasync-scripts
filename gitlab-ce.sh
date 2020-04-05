#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://packages.gitlab.com/gitlab/gitlab-ce"}

BASE_PATH="${TUNASYNC_WORKING_DIR}"

YUM_PATH="${BASE_PATH}/yum"
UBUNTU_PATH="${BASE_PATH}/ubuntu/"
DEBIAN_PATH="${BASE_PATH}/debian/"

"$yum_sync" "${UPSTREAM}/el/@{os_ver}/@{arch}/" 6-8 "gitlab" x86_64 "el@{os_ver}" "$YUM_PATH"
echo "YUM finished"

"$apt_sync" "${UPSTREAM}/ubuntu" @ubuntu-lts main amd64,i386 "$UBUNTU_PATH"
echo "Ubuntu finished"
"$apt_sync" "${UPSTREAM}/debian" @debian-current main amd64,i386 "$DEBIAN_PATH"
echo "Debian finished"


# vim: ts=4 sts=4 sw=4
