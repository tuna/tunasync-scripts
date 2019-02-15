#!/bin/bash
set -e

cd "$TUNASYNC_WORKING_DIR"
echo "rustup sync started"

BASE_URL=${MIRROR_BASE_URL:-"https://mirrors.tuna.tsinghua.edu.cn/rustup"}

/usr/local/cargo/bin/rustup-mirror -u "${BASE_URL}" -m "${TUNASYNC_WORKING_DIR}"
echo "finished"
