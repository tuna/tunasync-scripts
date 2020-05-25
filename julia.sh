#!/bin/bash
set -e
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"pkg.julialang.org"}
[[ -d "${TUNASYNC_WORKING_DIR}" ]]
cd "${TUNASYNC_WORKING_DIR}"
exec julia -e "using StorageServer; mirror_tarball(\"registries/General\", [\"$BASE_URL\"])"

