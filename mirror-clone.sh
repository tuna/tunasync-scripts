#!/bin/bash

set -euo pipefail

# Like tsumugu.sh: take the binary from PATH unless explicitly overridden
# (the image built from dockerfiles/mirror-clone installs it to
# /usr/local/bin/mirror-clone).
mirror_clone=${MIRRORCLONE_BIN:-mirror-clone}

TUNASYNC_MIRRORCLONE_OPTIONS=${TUNASYNC_MIRRORCLONE_OPTIONS:-}
TUNASYNC_MIRRORCLONE_SOURCE=${TUNASYNC_MIRRORCLONE_SOURCE:-}
TUNASYNC_MIRRORCLONE_ARGS=${TUNASYNC_MIRRORCLONE_ARGS:-}

if [ -z "$TUNASYNC_MIRRORCLONE_SOURCE" ]; then
    echo "Error: TUNASYNC_MIRRORCLONE_SOURCE is not set" >&2
    exit 1
fi

# Fail with an actionable message instead of a bare "unbound variable".
if [ -z "${TUNASYNC_WORKING_DIR:-}" ]; then
    echo "Error: TUNASYNC_WORKING_DIR is not set" >&2
    exit 1
fi

[ ! -d "${TUNASYNC_WORKING_DIR}" ] && mkdir -p "${TUNASYNC_WORKING_DIR}"
# Resolve to an absolute path before cd, so a relative TUNASYNC_WORKING_DIR
# cannot silently shift paths derived from it below.
TUNASYNC_WORKING_DIR=$(cd "${TUNASYNC_WORKING_DIR}" && pwd)
cd "${TUNASYNC_WORKING_DIR}"

# The file backend moves finished downloads into place with rename(2)
# (src/file_backend.rs), which cannot cross filesystems, so the buffer must
# share a filesystem with the base path. tunasync's docker provider only
# bind-mounts the working dir, hence the default is a hidden dir inside it.
# Upstream recommends keeping the buffer outside the base path (the backend
# scans every file under the base as mirror content): in-flight buffers are
# never in the precomputed target snapshot and leftover .buffer files are
# removed by the next run's deletion phase, but the directory is visible in
# the served tree. Set TUNASYNC_MIRRORCLONE_BUFFER to a mounted path outside
# the working dir (on the same filesystem) to avoid that.
buffer_dir=${TUNASYNC_MIRRORCLONE_BUFFER:-"${TUNASYNC_WORKING_DIR}/.mirror-clone-buffer"}
mkdir -p "$buffer_dir"

# set -f: the unquoted pass-through variables below are word-split on
# purpose (same as tsumugu.sh); don't also glob-expand them against the
# mirror dir.
set -f
exec "$mirror_clone" \
    --target-type file \
    --file-buffer-path "$buffer_dir" \
    --file-base-path "${TUNASYNC_WORKING_DIR}" \
    $TUNASYNC_MIRRORCLONE_OPTIONS \
    "$TUNASYNC_MIRRORCLONE_SOURCE" \
    $TUNASYNC_MIRRORCLONE_ARGS
