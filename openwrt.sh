#!/bin/bash

CURRENT_STABLE_RELEASES="17.01.5 18.06.0"

function sync_openwrt() {
	repo_url="$1"
	repo_dir="$2"

	[ ! -d "$repo_dir" ] && mkdir -p "$repo_dir"
	cd $repo_dir
	lftp "${repo_url}/" -e "mirror --verbose -P 5 --delete --only-missing; bye"
	lftp "${repo_url}/" -e "mirror --verbose -P 5 --only-newer --exclude-glob *.ipk; bye"
}

#sync_openwrt "http://downloads.openwrt.org/chaos_calmer/15.05.1" "${TUNASYNC_WORKING_DIR}/chaos_calmer/15.05.1"
for release in $CURRENT_STABLE_RELEASES; do sync_openwrt "http://downloads.openwrt.org/releases/$release/targets" "${TUNASYNC_WORKING_DIR}/release/$release"; done
