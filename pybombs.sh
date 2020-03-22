#!/bin/bash
# requires: git, svn, wget
# pybombs-mirror: https://github.com/scateu/pybombs-mirror/

set -e
set -o pipefail

function pybombs_mirror() {
	[[ ! -d ${TUNASYNC_WORKING_DIR} ]] && mkdir -p ${TUNASYNC_WORKING_DIR}
	export PYBOMBS_MIRROR_BASE_URL=${MIRROR_BASE_URL}
	export PYBOMBS_MIRROR_WORK_DIR=${TUNASYNC_WORKING_DIR}
	cp ${PYBOMBS_MIRROR_SCRIPT_PATH}/upstream-recipe-repos.urls ${TUNASYNC_WORKING_DIR}/
	cp ${PYBOMBS_MIRROR_SCRIPT_PATH}/pre-replace-upstream.urls ${TUNASYNC_WORKING_DIR}/
	cp ${PYBOMBS_MIRROR_SCRIPT_PATH}/ignore.urls ${TUNASYNC_WORKING_DIR}/
	${PYBOMBS_MIRROR_SCRIPT_PATH}/pybombs-mirror.sh
}
function calculate_size() {
	total_size=0
	for repo in "${TUNASYNC_WORKING_DIR}"/git/*; do
		sz=$(git -C "$repo" count-objects -v|grep -Po '(?<=size-pack: )\d+')
		total_size=$(($total_size+1024*$sz))
	done
	sz=$(du -sb "${TUNASYNC_WORKING_DIR}/wget"|cut -f1)
	total_size=$(($total_size+$sz))
	echo "Total size is" $(numfmt --to=iec $total_size)
}

PYBOMBS_MIRROR_SCRIPT_PATH="${PYBOMBS_MIRROR_SCRIPT_PATH:-"/opt/pybombs-mirror"}"
MIRROR_BASE_URL="${MIRROR_BASE_URL:-"https://pybombs.tuna.tsinghua.edu.cn"}"

pybombs_mirror
calculate_size
