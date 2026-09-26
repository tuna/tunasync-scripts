#!/bin/bash
set -e

cd "$TUNASYNC_WORKING_DIR"
echo "rustup sync started"

BASE_URL=${MIRROR_BASE_URL:-"https://mirrors.tuna.tsinghua.edu.cn/rustup"}
GC=${RUSTUP_GC:-"30"}
# rustup-mirror >= 0.12.0 retries transient per-file download failures with
# exponential backoff; --retries sets the per-file attempts (default 3).
RETRIES=${RUSTUP_RETRIES:-"3"}

/usr/local/cargo/bin/rustup-mirror -u "${BASE_URL}" -m "${TUNASYNC_WORKING_DIR}" --gc "${GC}" --retries "${RETRIES}"
echo "finished"
