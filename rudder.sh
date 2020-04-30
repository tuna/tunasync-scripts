#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://repository.rudder.io"}
RUDDER_VERS=(4.3 5.0 6.0)

YUM_PATH="${BASE_PATH}/rpm"
APT_PATH="${BASE_PATH}/apt"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

components=$(printf ",%s" "${RUDDER_VERS[@]}")
components=${components:1}
"$yum_sync" "${UPSTREAM}/rpm/@{comp}/RHEL_@{os_ver}/" 6-8 $components x86_64 "rudder@{comp}-RHEL_@{os_ver}" "$YUM_PATH"
echo "YUM finished"

for ver in ${RUDDER_VERS[@]}; do
    "$apt_sync" --delete "${UPSTREAM}/apt/${ver}" @ubuntu-lts,@debian-current main amd64 "$APT_PATH/${ver}"
done
echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm

# vim: ts=4 sts=4 sw=4
