#!/bin/bash
# requires: lftp, jq, python3.5, lxml, pyquery 
# set -x
set -e 
set -u 
set -o pipefail

_here=`dirname $(realpath $0)`
GET_FILELIST="${_here}/helpers/docker-ce-filelist.py"

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://download.docker.com/"}"

REMOTE_FILELIST="${TUNASYNC_WORKING_DIR}/.filelist.remote"
LOCAL_FILELIST="${TUNASYNC_WORKING_DIR}/.filelist.local"
[[ -f $REMOTE_FILELIST ]] && rm $REMOTE_FILELIST
[[ -f $LOCAL_FILELIST ]] && rm $LOCAL_FILELIST

function cleanup () {
	echo "cleaning up"
	[[ -f $REMOTE_FILELIST ]] && rm $REMOTE_FILELIST || true
	[[ -f $LOCAL_FILELIST ]] && rm $LOCAL_FILELIST || true
}

trap cleanup EXIT

# download
while read remote_url; do
	dst_rel_file=${remote_url#$BASE_URL}
	dst_file="${TUNASYNC_WORKING_DIR}/${dst_rel_file}"
	dst_dir=`dirname ${dst_file}`

	echo "${dst_rel_file}" >> $REMOTE_FILELIST

	if [[ -f ${dst_file} ]]; then
		remote_meta=`curl -sI "${remote_url}"`
		remote_filesize=`echo -e "$remote_meta" | grep -i '^content-length:' | awk '{print $2}' | tr -d '\n\r' || echo 0`
		remote_date=`echo -e "$remote_meta" | grep -i '^last-modified:' | sed 's/^last-modified: //I' | tr -d '\n\r' || echo 0`
		remote_date=`date --date="${remote_date}" +%s`

		local_filesize=`stat -c "%s" ${dst_file}`
		local_date=`stat -c "%Y" ${dst_file}`

		if (( ${remote_filesize} == ${local_filesize} && ${remote_date} == ${local_date} )) ; then
			echo "skipping ${dst_rel_file}"
			continue
		fi
		rm $dst_file
	else
		mkdir -p $dst_dir
	fi
	
	echo "downloading ${remote_url}"
	curl -o ${dst_file} -s -L --remote-time --show-error --fail ${remote_url} || {
		echo "Failed: ${remote_url}"
		[[ -f ${dst_file} ]] && rm ${dst_file}
	}
done < <($GET_FILELIST $BASE_URL)

# remove old files
(cd ${TUNASYNC_WORKING_DIR}; find . -type f ) | sed 's+^\./++' > ${LOCAL_FILELIST}
comm <(sort $REMOTE_FILELIST) <(sort $LOCAL_FILELIST) -13 | while read file; do
	file="${TUNASYNC_WORKING_DIR}/$file"
	echo "deleting ${file}"
	[[ -f $file ]] && rm ${file}
done
