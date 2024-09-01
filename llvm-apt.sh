#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://apt.llvm.org"}

export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

for os in "jammy" "noble" "bullseye" "bookworm"; do
    prefix=llvm-toolchain-$os
    "$apt_sync" --delete "$BASE_URL/$os" $prefix,$prefix-9,$prefix-10,$prefix-11,$prefix-12,$prefix-13,$prefix-14,$prefix-15,$prefix-16,$prefix-17,$prefix-18,$prefix-19 main amd64,arm64 "$BASE_PATH/$os"
done

echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
