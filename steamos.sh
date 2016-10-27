#!/bin/bash

function sync_steamos() {
	repo_url="$1"
	repo_dir="$2"

	[ ! -d "$repo_dir" ] && mkdir -p "$repo_dir"
	cd $repo_dir
	lftp "${repo_url}/" -e "mirror --verbose --exclude icons/ -P 5 --delete --only-newer; bye"
}

BASE_URL=${TUNASYNC_UPSTREAM_URL:-"http://repo.steampowered.com"}
sync_steamos "${BASE_URL}" "${TUNASYNC_WORKING_DIR}"
