#!/bin/bash

function sync_vlc() {
    mkdir -p "${TUNASYNC_WORKING_DIR}/$2/"
    rsync -a --delete "${TUNASYNC_UPSTREAM_URL}/$1/" "${TUNASYNC_WORKING_DIR}/$2/"
}

sync_vlc "vlc/last" "vlc/last"
sync_vlc "vlc-android/last" "vlc-android/last"

total_size=$(du -shL "${TUNASYNC_WORKING_DIR}" | cut -f1)
echo "Total size is $total_size"
