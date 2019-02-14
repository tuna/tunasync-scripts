#!/bin/bash
set -e

echo "rustup sync started"
/usr/local/cargo/bin/rustup-mirror -u https://mirrors.tuna.tsinghua.edu.cn/rustup -m ${TUNASYNC_WORKING_DIR}
echo "finished"
