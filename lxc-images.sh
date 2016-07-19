#!/bin/bash
# requires: lftp wget

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"http://images.linuxcontainers.org/"}"

function sync_lxc_images() {
	repo_url="$1"
	repo_dir="$2"

	[ ! -d "$repo_dir" ] && mkdir -p "$repo_dir"
	cd $repo_dir

	lftp "${repo_url}/" -e "mirror --verbose -P 5 --delete --only-newer; bye"
}

sync_lxc_images "${BASE_URL}/images" "${TUNASYNC_WORKING_DIR}/images"

mkdir -p "${TUNASYNC_WORKING_DIR}/meta/1.0"
wget -O "${TUNASYNC_WORKING_DIR}/meta/1.0/index-system" "${BASE_URL}/meta/1.0/index-system"
wget -O "${TUNASYNC_WORKING_DIR}/meta/1.0/index-user" "${BASE_URL}/meta/1.0/index-user"
