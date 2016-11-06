#!/bin/bash
# requires: wget, python3
set -u
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/helpers

XMLPARSE="${_here}/helpers/tf-xml-filelist.py"

TF_UPSTREAM_BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://storage.googleapis.com/tensorflow"}
BASE_PATH="${TUNASYNC_WORKING_DIR}"

# remove ending slash
BASE_PATH=${BASE_PATH%/}
TF_UPSTREAM_BASE_URL=${TF_UPSTREAM_BASE_URL%/}

failed=0
wget -O - "${TF_UPSTREAM_BASE_URL}/" | ${XMLPARSE} | while read -a tokens; do
	filename=${tokens[0]}
	filesize=${tokens[1]}
	
	# Notice: the filename starts with no leading '/'!
	pkgurl="${TF_UPSTREAM_BASE_URL}/${filename}"
	pkgdst="${BASE_PATH}/${filename}"
	pkgdir=`dirname ${pkgdst}`
	mkdir -p ${pkgdir}
	
	echo "downloading ${pkgurl}"
	if [[ -z ${DRY_RUN:-} ]]; then
		check-and-download ${pkgurl} ${pkgdst} || failed=1
	fi
done
exit $failed










