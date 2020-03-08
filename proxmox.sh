#!/bin/bash
# requires: wget, timeout
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[[ -z "${LOADED_APT_DOWNLOAD}" ]] && { echo "failed to load apt-download"; exit 1; }

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"http://download.proxmox.com"}"
BASE_PATH="${TUNASYNC_WORKING_DIR}"

APT_PATH="${BASE_PATH}/debian"

APT_VERSIONS=("buster" "stretch" "jessie")

# === download deb packages ====

mkdir -p "${APT_PATH}"
for version in ${APT_VERSIONS[@]}; do
	apt-download-binary "${BASE_URL}/debian" "$version" "pve-no-subscription" "amd64" "${APT_PATH}" || true
	apt-download-binary "${BASE_URL}/debian" "$version" "pvetest" "amd64" "${APT_PATH}" || true
done
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
