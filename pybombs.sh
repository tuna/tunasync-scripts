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

PYBOMBS_MIRROR_SCRIPT_PATH="${PYBOMBS_MIRROR_SCRIPT_PATH:-"/opt/pybombs-mirror"}"
MIRROR_BASE_URL="${MIRROR_BASE_URL:-"https://pybombs.tuna.tsinghua.edu.cn"}"

pybombs_mirror
