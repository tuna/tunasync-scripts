#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://apt.llvm.org"}

export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

function get_codenames() {
    local os=$1
    local dist_meta_url="${BASE_URL}/${os}/conf/distributions"
    local codenames=$(curl -sSfL $dist_meta_url 2>/dev/null | grep -oP '^Codename: \K.*' | tr '\n' ',' | sed 's/,$//')
    if [ -z "$codenames" ]; then
        echo "Unable to fetch codename from $dist_meta_url, using default" >&2
        prefix=llvm-toolchain-$os
        codenames="$prefix,$prefix-18,$prefix-19,$prefix-20"
    fi
    echo "Codenames for $os: $codenames" >&2
    echo $codenames
}

for os in "focal" "jammy" "noble" "bullseye" "bookworm"; do
    codenames=$(get_codenames $os)
    "$apt_sync" --delete "$BASE_URL/$os" "$codenames" main amd64,arm64 "$BASE_PATH/$os"
done

echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
