#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"
yum_sync="${_here}/yum-sync.py"

UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://packages.gitlab.com/gitlab/gitlab-ce"}

BASE_PATH="${TUNASYNC_WORKING_DIR}"

DEB_ARCHES=${DEB_ARCHES:-"amd64,i386,arm64"}

YUM_PATH="${BASE_PATH}/yum"
UBUNTU_PATH="${BASE_PATH}/ubuntu/"
DEBIAN_PATH="${BASE_PATH}/debian/"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

"$yum_sync" "${UPSTREAM}/el/@{os_ver}/@{arch}/" @rhel-current "gitlab" x86_64 "el@{os_ver}" "$YUM_PATH"
echo "YUM finished"

for i in jammy noble; do
    "$apt_sync" --delete "${UPSTREAM}/ubuntu/$i" "$i" main "$DEB_ARCHES" "$UBUNTU_PATH/$i"
done
echo "Ubuntu finished"
for i in bullseye bookworm trixie; do
    "$apt_sync" --delete "${UPSTREAM}/debian/$i" "$i" main "$DEB_ARCHES" "$DEBIAN_PATH/$i"
done
echo "Debian finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm

# vim: ts=4 sts=4 sw=4
