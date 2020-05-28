#!/bin/bash
set -e
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://pkg.julialang.org"}
[[ -d "${TUNASYNC_WORKING_DIR}" ]]
cd "${TUNASYNC_WORKING_DIR}"

export JULIA_STATIC_DIR="$PWD/static"
export JULIA_CLONES_DIR="$PWD/clones"

# update and mirror the General registry
git -C registries/General fetch --all
git -C registries/General reset --hard origin/master
exec julia -e "using StorageServer; mirror_tarball(\"registries/General\", [\"$BASE_URL\"])"

