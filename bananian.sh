#!/bin/bash

function sync_bananian() {
	repo_url="$1"
	repo_dir="$2"

	[ ! -d "$repo_dir" ] && mkdir -p "$repo_dir"
	cd $repo_dir
	lftp "${repo_url}/" -e "mirror --verbose  -P 5 --delete; bye"
}

sync_bananian "https://dl.bananian.org" "${TUNASYNC_WORKING_DIR}"
