#!/bin/bash
set -e
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"pkg.julialang.org"}
[[ -d "${TUNASYNC_WORKING_DIR}" ]]
cd "${TUNASYNC_WORKING_DIR}"

export JULIA_STATIC_DIR="$PWD/static"
export JULIA_CLONES_DIR="$PWD/clones"
exec julia -e "using StorageServer; mirror_tarball(\"registries/General\", [\"$BASE_URL\"])"

