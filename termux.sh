#!/bin/bash
set -e

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download
[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

BASE_PATH="${TUNASYNC_WORKING_DIR}"

base_url=${TUNASYNC_UPSTREAM_URL:-"https://termux.net"}

ARCHES=("aarch64" "all" "arm" "i686")

remote_filelist="${BASE_PATH}/filelist.remote"
local_filelist="${BASE_PATH}/filelist.local"

for arch in ${ARCHES[@]}; do
	echo "start syncing: ${arch}"
	apt-download-binary "${base_url}" "stable" "main" "${arch}" "${BASE_PATH}" ${remote_filelist} || true
done

BACKUP_PATH="${BASE_PATH}/backup/"
mkdir -p ${BACKUP_PATH}
(cd ${BASE_PATH}; find . -type f -iname "*.deb") | sed 's+^\./++' > ${local_filelist}
comm <(sort $remote_filelist) <(sort $local_filelist) -13 | while read file; do
	echo "deleting ${file}"
	mv "${BASE_PATH}/$file" ${BACKUP_PATH}
done

echo "finished"
