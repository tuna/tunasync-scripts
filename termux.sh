#!/bin/bash
set -e

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download
[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

WORKING_DIR="${TUNASYNC_WORKING_DIR}"

ARCHES=("aarch64" "all" "arm" "i686" "x86_64")

function sync_one_repo() {
	base_url="$1"
	BASE_PATH="$2"
	suite="$3"
	component="$4"
	[[ ! -d "$BASE_PATH" ]] && mkdir -p "$BASE_PATH"
	remote_filelist="${BASE_PATH}/filelist"
	[[ -f $remote_filelist ]] && rm $remote_filelist

	for arch in ${ARCHES[@]}; do
		echo "start syncing: $base_url ${arch}"
		apt-download-binary "${base_url}" "$suite" "$component" "${arch}" "${BASE_PATH}" ${remote_filelist} || true
	done

	apt-delete-old-debs ${BASE_PATH} $remote_filelist
}

sync_one_repo "https://dl.bintray.com/termux/termux-packages-24" "${WORKING_DIR}/termux-packages-24" stable main
sync_one_repo "https://dl.bintray.com/xeffyr/unstable-packages" "${WORKING_DIR}/unstable-packages" unstable main
sync_one_repo "https://dl.bintray.com/xeffyr/x11-packages" "${WORKING_DIR}/x11-packages" x11 main
sync_one_repo "https://dl.bintray.com/grimler/science-packages-24" "${WORKING_DIR}/science-packages-24" science stable
sync_one_repo "https://dl.bintray.com/grimler/game-packages-24" "${WORKING_DIR}/game-packages-24" games stable
sync_one_repo "https://dl.bintray.com/grimler/termux-root-packages-24" "${WORKING_DIR}/termux-root-packages-24" root stable

echo "finished"
