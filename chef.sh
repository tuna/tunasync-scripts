#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://packages.chef.io/repos"}

YUM_PATH="${BASE_PATH}/yum/stable"
APT_PATH="${BASE_PATH}/apt/stable"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

"$yum_sync" "${UPSTREAM}/yum/stable/el/@{os_ver}/@{arch}" @rhel-current chef x86_64 "stable-el@{os_ver}-@{arch}" "$YUM_PATH"
echo "YUM finished"

"$apt_sync" --delete "${UPSTREAM}/apt/stable" @ubuntu-lts,@debian-current main amd64,i386,aarch64 "$APT_PATH"
echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm

# vim: ts=4 sts=4 sw=4
