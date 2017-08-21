#!/bin/bash
# requires: wget, lftp, jq, python3.5, lxml, pyquery 
# set -x
set -e 
set -u 
set -o pipefail

_here=`dirname $(realpath $0)`
GET_FILELIST="${_here}/helpers/docker-ce-filelist.py"

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://download.docker.com/linux/"}"

TMP_DIR="${TUNASYNC_WORKING_DIR}/.tmp"
mkdir -p $TMP_DIR

REMOTE_FILELIST="${TUNASYNC_WORKING_DIR}/.filelist.remote"
LOCAL_FILELIST="${TUNASYNC_WORKING_DIR}/.filelist.local"
[[ -f $REMOTE_FILELIST ]] && rm $REMOTE_FILELIST
[[ -f $LOCAL_FILELIST ]] && rm $LOCAL_FILELIST

function cleanup () {
	echo "cleaning up"
	[[ -d ${TMP_DIR} ]] && {
		rm -rf $TMP_DIR
	}
	[[ -f $REMOTE_FILELIST ]] && rm $REMOTE_FILELIST
	[[ -f $LOCAL_FILELIST ]] && rm $LOCAL_FILELIST
}

trap cleanup EXIT

# download
$GET_FILELIST $BASE_URL | while read remote_url; do
	dst_rel_file=${remote_url#$BASE_URL}
	dst_file="${TUNASYNC_WORKING_DIR}/${dst_rel_file}"
	dst_tmp_file="${TMP_DIR}/$(basename ${dst_file})"

	echo "${dst_rel_file}" >> $REMOTE_FILELIST

	echo "downloading ${remote_url}"
	[[ -f ${dst_file} ]] && cp -a ${dst_file} ${dst_tmp_file} || mkdir -p `dirname ${dst_file}`
	(cd ${TMP_DIR} && wget -q -N ${remote_url} && mv ${dst_tmp_file} ${dst_file})
done

rm -rf $TMP_DIR

(cd ${TUNASYNC_WORKING_DIR}; find . -type f ) | sed 's+^\./++' > ${LOCAL_FILELIST}
comm <(sort $REMOTE_FILELIST) <(sort $LOCAL_FILELIST) -13 | while read file; do
	file="${TUNASYNC_WORKING_DIR}/$file"
	echo "deleting ${file}"
	[[ -f $file ]] && rm ${file}
done
