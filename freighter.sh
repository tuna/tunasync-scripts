#!/bin/bash
set -e
FREIGHTER=${FREIGHTER:-"/usr/local/cargo/bin/freighter-registry"}
CRATES_UPSTREAM="https://static.crates.io/crates"
INDEX_UPSTREAM="https://mirrors.tuna.tsinghua.edu.cn/git/crates.io-index.git"
TUNASYNC_UPSTREAM=${TUNASYNC_UPSTREAM_URL:-$CRATES_UPSTREAM}
TUNASYNC_UPSTREAM=${TUNASYNC_UPSTREAM%/}
CONF="$TUNASYNC_WORKING_DIR/config.toml"
INIT=${INIT:-"0"}

if [ ! -d "$TUNASYNC_WORKING_DIR" ]; then
	mkdir -p $TUNASYNC_WORKING_DIR
	INIT="1"
elif [ -d "$TUNASYNC_WORKING_DIR/crates" ]; then
	INIT="1"
fi

echo "Syncing to $TUNASYNC_WORKING_DIR"

cat > $CONF << EOF
[log]
# see https://docs.rs/log4rs/1.2.0/log4rs/append/file/struct.FileAppenderDeserializer.html#configuration
encoder = "{d}:{l} - {m}{n}"
# unit is MB
limit = 100
level = "info"
[crates]
index_domain = "$INDEX_UPSTREAM"
domain = "$CRATES_UPSTREAM"
download_threads = 16
serve_domains = [
    "localhost",
    ]
[proxy]
enable = false
# git_index_proxy = "127.0.0.1:6780"
# download_proxy = "127.0.0.1:6780"
EOF

if [[ $INIT == "0" ]]; then
	$FREIGHTER -c $TUNASYNC_WORKING_DIR crates pull
	exec $FREIGHTER -c $TUNASYNC_WORKING_DIR crates download
else
	$FREIGHTER -c $TUNASYNC_WORKING_DIR crates pull
	exec $FREIGHTER -c $TUNASYNC_WORKING_DIR crates download --init
fi
