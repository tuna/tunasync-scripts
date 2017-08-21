#!/bin/bash
# requires: lftp wget jq

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://download.docker.com/linux/"}"

function sync_docker_ce() {
	repo_url="$1"
	repo_dir="$2"

	[ ! -d "$repo_dir" ] && mkdir -p "$repo_dir"
	cd $repo_dir

	lftp "${repo_url}/" -e "mirror --verbose -P 5 --delete --only-newer; bye"
}

sync_docker_ce "${BASE_URL}" "${TUNASYNC_WORKING_DIR}/"
