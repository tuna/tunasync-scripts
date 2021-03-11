#!/bin/bash
set -e
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://us-east.storage.juliahub.com"}
[[ -d "${TUNASYNC_WORKING_DIR}" ]]
cd "${TUNASYNC_WORKING_DIR}"

UPSTREAMS="[\"https://us-east.storage.juliahub.com\", \"https://kr.storage.juliahub.com\"]"

OUTPUT_DIR="$PWD/static"

REGISTRY_NAME="General"
REGISTRY_UUID="23338594-aafe-5451-b93e-139f81909106"
REGISTRY_UPSTREAM="https://github.com/JuliaRegistries/General"
REGISTRY="(\"$REGISTRY_NAME\", \"$REGISTRY_UUID\", \"$REGISTRY_UPSTREAM\")"

# For more usage of `mirror_tarball`, please refer to
# https://github.com/johnnychen94/StorageMirrorServer.jl/blob/master/examples/gen_static_full.example.jl
exec julia -e "using StorageMirrorServer; mirror_tarball($REGISTRY, $UPSTREAMS, \"$OUTPUT_DIR\", skip_duration=120)"
