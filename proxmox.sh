#!/bin/bash
# requires: wget, timeout
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"http://download.proxmox.com"}"
BASE_PATH="${TUNASYNC_WORKING_DIR}"

APT_PATH="${BASE_PATH}/debian"

# === download deb packages ====

"$apt_sync" "${BASE_URL}/debian" @debian-current pve-no-subscription,pvetest amd64 "$APT_PATH"
echo "Debian finished"

# === download standalone files ====

function sync_files() {
	repo_url="$1"
	repo_dir="$2"

	[ ! -d "$repo_dir" ] && mkdir -p "$repo_dir"
	cd $repo_dir
	lftp "${repo_url}/" -e "mirror --verbose -P 5 --delete --only-newer; bye"
}

sync_files "${BASE_URL}/images" "${BASE_PATH}/images"
sync_files "${BASE_URL}/iso" "${BASE_PATH}/iso"

echo "Proxmox finished"
