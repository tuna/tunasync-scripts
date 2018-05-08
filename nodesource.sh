#!/bin/bash

function sync_nodesource() {
	repo_url="$1"
	repo_dir="$2"
	lftp_opts="$3"

	[[ ! -d "$repo_dir" ]] && mkdir -p "$repo_dir"
	cd $repo_dir
	lftp "${repo_url}/" -e "mirror --verbose $lftp_opts -P 5 --delete --only-newer; bye"
}

DEB_BASE_URL="https://deb.nodesource.com"
RPM_BASE_URL="https://rpm.nodesource.com"

node_versions=("0.10" "0.12" "4.x" "6.x" "7.x" "8.x" "9.x" "10.x")
declare success=true

for ver in ${node_versions[@]}; do
	sync_nodesource "${DEB_BASE_URL}/node_${ver}" "${TUNASYNC_WORKING_DIR}/deb_${ver}" "--exclude db/ --exclude conf/" || success=false
done

for ver in ${node_versions[@]}; do
	sync_nodesource "${RPM_BASE_URL}/pub_${ver}" "${TUNASYNC_WORKING_DIR}/rpm_${ver}" || success=false
done

[[ $success == true ]] && exit 0 || exit 1
