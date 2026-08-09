#!/bin/bash

set -euo pipefail

_here=$(dirname "$(realpath "$0")")
mirror_clone="${MIRRORCLONE_BIN:-${_here}/mirror-clone}"

TUNASYNC_MIRRORCLONE_OPTIONS=${TUNASYNC_MIRRORCLONE_OPTIONS:-}
TUNASYNC_MIRRORCLONE_SOURCE=${TUNASYNC_MIRRORCLONE_SOURCE:-}
TUNASYNC_MIRRORCLONE_ARGS=${TUNASYNC_MIRRORCLONE_ARGS:-}

if [ -z "$TUNASYNC_MIRRORCLONE_SOURCE" ]; then
    echo "Error: TUNASYNC_MIRRORCLONE_SOURCE is not set" >&2
    exit 1
fi

[ ! -d "${TUNASYNC_WORKING_DIR}" ] && mkdir -p "${TUNASYNC_WORKING_DIR}"
cd "${TUNASYNC_WORKING_DIR}"

exec "$mirror_clone" \
    --target-type file \
    --file-buffer-path "${TUNASYNC_WORKING_DIR}/.tmp" \
    --file-base-path "${TUNASYNC_WORKING_DIR}" \
    $TUNASYNC_MIRRORCLONE_OPTIONS \
    "$TUNASYNC_MIRRORCLONE_SOURCE" \
    $TUNASYNC_MIRRORCLONE_ARGS
