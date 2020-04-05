#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://packages.chef.io/repos"}

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"

"$yum_sync" "${UPSTREAM}/yum/stable/el/@{os_ver}/@{arch}" 6-8 chef x86_64 "stable-el@{os_ver}-@{arch}" "$YUM_PATH"
echo "YUM finished"

"$apt_sync" "${UPSTREAM}/apt/stable" @ubuntu-lts,@debian-current main amd64,i386,aarch64 "$APT_PATH"
echo "APT finished"

# vim: ts=4 sts=4 sw=4
