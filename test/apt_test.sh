#!/bin/bash
# reqires: wget, yum-utils

set -e
set -o pipefail

_here=`dirname $(realpath $0)`
_here=`dirname ${_here}`

. ${_here}/helpers/apt-download
APT_VERSIONS=("debian-jessie" "debian-stretch" "ubuntu-xenial")

BASE_PATH="${TUNASYNC_WORKING_DIR}"
APT_PATH="${BASE_PATH}/apt/repo"

mkdir -p ${APT_PATH}

# APT mirror 
if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi
base_url="https://apt.dockerproject.org/repo"
remote_filelist="${APT_PATH}/filelist.remote"
local_filelist="${APT_PATH}/filelist.local"

for version in ${APT_VERSIONS[@]}; do
	apt-download-binary ${base_url} "$version" "main" "amd64" "${APT_PATH}" ${remote_filelist} || true
	apt-download-binary ${base_url} "$version" "main" "i386" "${APT_PATH}" ${remote_filelist} || true
done

APT_BACKUP_PATH="${BASE_PATH}/backup/apt"
mkdir -p ${APT_BACKUP_PATH}
(cd ${APT_PATH}; find . -type f -iname "*.deb") | sed 's+^\./++' > ${local_filelist}
comm <(sort $remote_filelist) <(sort $local_filelist) -13 | while read file; do
	echo "deleting ${file}"
	mv "${APT_PATH}/$file" ${APT_BACKUP_PATH}
done

rm ${remote_filelist} ${local_filelist}
