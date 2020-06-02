#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://apt.llvm.org"}

export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

for os in "xenial" "bionic" "focal" "stretch" "buster"; do
    for ver in "" "-9" "-10"; do
        "$apt_sync" --delete "$BASE_URL/$os" llvm-toolchain-$os$ver main amd64 "$BASE_PATH/$os"
    done
done

echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
