#!/usr/bin/env bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
github_release="${_here}/github-release.py"
github_release_config="${_here}/riscv-toolchains.json"
git_recursive="${_here}/git-recursive.sh"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
GIT_PATH="${BASE_PATH}/git"
RELEASE_PATH="${BASE_PATH}/release"

mkdir -p $BASE_PATH
mkdir -p $GIT_PATH
mkdir -p $RELEASE_PATH

# git
declare -a upstreams=(
    "https://github.com/riscv-collab/riscv-gnu-toolchain.git"
    "https://github.com/riscv/riscv-isa-manual.git"
    "https://github.com/riscv/riscv-opcodes.git"
    "https://github.com/riscv/riscv-openocd.git"
    "https://github.com/riscv/sail-riscv.git"
    "https://github.com/riscv-non-isa/riscv-arch-test.git"
    "https://github.com/riscv-software-src/riscv-tools.git"
    "https://github.com/riscv-software-src/riscv-isa-sim.git"
    "https://github.com/riscv-software-src/opensbi.git"
    "https://github.com/riscv-software-src/riscv-tests.git"
    "https://github.com/chipsalliance/rocket-tools.git"
)

export RECURSIVE=1
export MIRROR_BASE_URL=${MIRROR_BASE_URL:-"https://mirror.iscas.ac.cn/riscv-toolchains/git"}
export WORKING_DIR_BASE=$GIT_PATH
for upstream in "${upstreams[@]}"; do
    ORG=$(basename $(dirname $upstream))
    REPO=$(basename $upstream)
    REPO_NO_GIT=$(basename upstream .git)
    SCRIPT=${REPO_NO_GIT}.sh
    export TUNASYNC_UPSTREAM_URL=$upstream
    export TUNASYNC_WORKING_DIR=$GIT_PATH/$ORG/$REPO
    export GENERATED_SCRIPT=$GIT_PATH/$ORG/$SCRIPT
    mkdir -p $WORKING_DIR_BASE
    echo $WORKING_DIR_BASE
    $git_recursive
done

# release
unset TUNASYNC_UPSTREAM_URL
export TUNASYNC_WORKING_DIR=$RELEASE_PATH
$github_release --config $github_release_config
