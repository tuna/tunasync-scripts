#!/bin/bash
# requires: wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packages.openmediavault.org/public"}
DISTS=arrakis-proposed,arrakis,usul-proposed,usul
EXTRA_PREFIX=(arrakis-beta arrakis-testing arrakis usul-testing usul-extras usul-beta usul)
ARCHS=amd64,i386,arm64,armel,armhf
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

# =================== official repos ===============================
"$apt_sync" --delete "${BASE_URL}" "$DISTS" main,partner $ARCHS "${BASE_PATH}/public"
# =================== extra repos ===============================
for i in "${EXTRA_PREFIX[@]}"
do
    "$apt_sync" --delete "https://dl.bintray.com/openmediavault-plugin-developers/$i" \
        @debian-latest2 main $ARCHS "${BASE_PATH}/openmediavault-plugin-developers/$i"
done
echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
