#!/bin/bash
set -e

BASE_URL=${MIRROR_BASE_URL:-"https://mirrors.tuna.tsinghua.edu.cn/dart-pub"}
UPSTREAM_URL=${TUNASYNC_UPSTREAM_URL:-"https://pub.dartlang.org/api"}
echo "From $UPSTREAM_URL to $BASE_URL"
if [[ $RANDOM -lt 683 ]]; then echo 'Refresh Index Files'; EXTRA=--overwrite; fi
exec /pub-cache/bin/pub_mirror --upstream "$UPSTREAM_URL" --verbose $EXTRA --delete --connections 10 --concurrency 5 "$TUNASYNC_WORKING_DIR" "$BASE_URL"
