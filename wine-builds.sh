#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://dl.winehq.org/wine-builds"}

export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

"$apt_sync" --delete "$BASE_URL/ubuntu" @ubuntu-lts main amd64,i386 "$BASE_PATH/ubuntu"
echo "APT for Ubuntu finished"

"$apt_sync" --delete "$BASE_URL/debian" @debian-latest2 main amd64,i386 "$BASE_PATH/debian"
echo "APT for Debian finished"

echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
