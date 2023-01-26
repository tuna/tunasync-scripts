#!/bin/bash
# requires: wget, timeout
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"http://download.proxmox.com"}"
BASE_PATH="${TUNASYNC_WORKING_DIR}"

APT_PATH="${BASE_PATH}/debian"
PVE_PATH="${APT_PATH}/pve"
PBS_PATH="${APT_PATH}/pbs"
PBS_CLIENT_PATH="${APT_PATH}/pbs-client"
PMG_PATH="${APT_PATH}/pmg"

# === download deb packages ====

"$apt_sync" --delete "${BASE_URL}/debian/pve" @debian-current pve-no-subscription,pvetest amd64 "$PVE_PATH"
"$apt_sync" --delete "${BASE_URL}/debian/pbs" @debian-current pbs-no-subscription amd64 "$PBS_PATH"
"$apt_sync" --delete "${BASE_URL}/debian/pbs-client" @debian-current main amd64 "$PBS_CLIENT_PATH"
"$apt_sync" --delete "${BASE_URL}/debian/pmg" @debian-current pmg-no-subscription amd64 "$PMG_PATH"
# upstream directory structure
ln -sf pve/dists $APT_PATH/dists
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
