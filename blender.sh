#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
BASE_PATH="${TUNASYNC_WORKING_DIR:-/srv/www/blender}"
# 修改为 rsync 源
RSYNC_URL="${TUNASYNC_UPSTREAM_URL:-rsync://mirrors.dotsrc.org/blender/release/}"

# 获取最新版本文件夹名
get_latest_version() {
    # 使用 rsync 列出目录
    rsync --list-only "$RSYNC_URL" | \
    awk '{print $5}' | \
    grep '^Blender[0-9]' | \
    grep -v 'alpha\|beta\|Benchmark\|Publisher\|plugin\|yafray' | \
    sort -V | \
    tail -n1
}

# 清理旧版本
clean_old_versions() {
    local latest="$1"
    for dir in "$BASE_PATH"/Blender*/; do
        if [ -d "$dir" ]; then
            dir_name=$(basename "$dir")
            if [ "$dir_name" != "$latest" ]; then
                echo "Removing old version: $dir_name"
                rm -rf "$dir"
            fi
        fi
    done
}

# 同步特定版本
sync_version() {
    local version="$1"
    local dest="$BASE_PATH/$version"
    local remote_path="$RSYNC_URL/$version/"

    mkdir -p "$dest"

    echo "Syncing $version from $remote_path"

    # 使用 rsync 同步，排除 .tar.xz 和 .zip 文件
    # 参数说明：
    # -a: 归档模式
    # -P: 显示进度
    # --delete: 删除目标目录中源没有的文件
    # --exclude: 排除特定文件类型
    # --quiet: 减少输出信息
    rsync -aP \
        --delete \
        --quiet \
        --exclude="*.tar.xz" \
        --exclude="*.zip" \
        "$remote_path" \
        "$dest/"

    # 检查 rsync 执行结果
    if [ $? -eq 0 ]; then
        local total_size
        total_size=$(du -sh "$dest" | cut -f1)
        echo "Successfully synced $version"
        echo "Total size is $total_size"
        return 0
    else
        echo "Failed to sync $version"
        return 1
    fi
}

# 主同步逻辑
echo "Starting sync"

# 获取最新版本
LATEST_VERSION=$(get_latest_version)
echo "Latest: $LATEST_VERSION"

if [ -z "$LATEST_VERSION" ]; then
    echo "Error: Could not detect latest Blender version"
    exit 1
fi

# 清理旧版本
clean_old_versions "$LATEST_VERSION"

# 同步最新版本
if sync_version "$LATEST_VERSION"; then
    echo "Sync finished"
else
    echo "Sync failed"
    exit 1
fi
