#!/bin/bash
# Run in Docker image: tunathu/homebrew-mirror
set -e
set -o pipefail

export HOMEBREW_REPO=${HOMEBREW_REPO:-"https://github.com/Homebrew"}
export HOMEBREW_TAPS=${HOMEBREW_TAPS:-"core"}
export HOMEBREW_BOTTLE_DOMAIN=${TUNASYNC_UPSTREAM_URL:-"https://linuxbrew.bintray.com"}

# Refer to https://github.com/gaoyifan/homebrew-bottle-mirror/blob/master/.docker/run

for tap in $HOMEBREW_TAPS;
do
    if [[ "$tap" = core ]];then # special case for homebrew-core
        export HOMEBREW_CACHE="${TUNASYNC_WORKING_DIR}/bottles"
    else
        export HOMEBREW_CACHE="${TUNASYNC_WORKING_DIR}/bottles-$tap"
        export HOMEBREW_TAP="$tap"
    fi
    if [[ "$RUN_LINUXBREW" = true ]];then
        repo_name="linuxbrew-${tap}"
        args="linux"
    else
        repo_name="homebrew-${tap}"
        args="mac"
    fi

    echo "===== SYNC STARTED AT $(date -R) ====="
    dir_core=/home/homebrew/.linuxbrew/homebrew/Library/Taps/homebrew/homebrew-core
    rm -fr "$dir_core" &>/dev/null || true
    echo "> update package info from $HOMEBREW_REPO/$repo_name.git..."
    git clone --depth 1 "$HOMEBREW_REPO/$repo_name.git" "$dir_core"
    echo ""
    echo "> RUN brew bottle-mirror $args..."
    /home/homebrew/.linuxbrew/bin/brew bottle-mirror "$args"
done
