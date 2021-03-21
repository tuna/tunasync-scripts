#!/bin/bash
# requires: wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packages.openmediavault.org/public"}
DISTS=arrakis-proposed,arrakis,usul-proposed,usul
EXTRA_DISTS=arrakis-docker,arrakis-plex,arrakis-sync,arrakis-teamviewer,arrakis,erasmus-backports,erasmus-beta,erasmus-ce-docker,erasmus-hwraid,erasmus-plex,erasmus-sync,erasmus-teamviewer,erasmus,usul-beta,usul-extras,usul-testing,usul
ARCHS=amd64,i386,arm64,armel,armhf
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

# =================== official repos ===============================
"$apt_sync" --delete "${BASE_URL}" "$DISTS" main,partner $ARCHS "${BASE_PATH}/public"
"$apt_sync" --delete "https://openmediavault.github.io/packages" "$DISTS" main,partner $ARCHS "${BASE_PATH}/packages"
# =================== extra repos ===============================
"$apt_sync" --delete "https://openmediavault-plugin-developers.github.io/packages/debian/$i" \
    "$EXTRA_DISTS" main $ARCHS "${BASE_PATH}/openmediavault-plugin-developers"
echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
