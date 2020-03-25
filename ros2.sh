#!/bin/bash
# requires: wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"http://packages.ros.org/ros2"}

APT_PATH="${BASE_PATH}/ubuntu"

APT_VERSIONS=(bionic buster cosmic disco eoan focal stretch xenial)

# =================== APT repos ===============================
if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi
mkdir -p ${APT_PATH}
base_url="${BASE_URL}/ubuntu"
for version in ${APT_VERSIONS[@]}; do
	for arch in "amd64" "arm64" "armhf"; do
		echo "=== Syncing $version $arch"
		apt-download-binary "${base_url}" "$version" "main" "$arch" "${APT_PATH}" || true
	done
done
echo "APT finished"
