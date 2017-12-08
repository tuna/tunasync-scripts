#!/bin/bash

function sync_winehq() {
	repo_url="$1"
	repo_dir="$2"

	[ ! -d "$repo_dir" ] && mkdir -p "$repo_dir"
	cd $repo_dir
	lftp "${repo_url}/" -e "mirror --verbose --skip-noaccess -x wine-builds.old/ -x /\\..+ -P 5 --delete ; bye"
}

BASE_URL=${TUNASYNC_UPSTREAM_URL:-"ftp://ftp.winehq.org/pub/"}
sync_winehq "${BASE_URL}" "${TUNASYNC_WORKING_DIR}"
