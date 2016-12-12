#!/bin/bash
set -e

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download
[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

BASE_PATH="${TUNASYNC_WORKING_DIR}"

base_url=${TUNASYNC_UPSTREAM_URL:-"https://termux.net"}

ARCHES=("aarch64" "all" "arm" "i686" "x86_64")

remote_filelist="${BASE_PATH}/filelist"
[[ -f $remote_filelist ]] && rm $remote_filelist

for arch in ${ARCHES[@]}; do
	echo "start syncing: ${arch}"
	apt-download-binary "${base_url}" "stable" "main" "${arch}" "${BASE_PATH}" ${remote_filelist} || true
done

apt-delete-old-debs ${BASE_PATH} $remote_filelist

echo "finished"
