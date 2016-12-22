#!/bin/bash
# requires: wget, python3
set -u
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
XMLPARSE="${_here}/helpers/tf-xml-filelist.py"
INDEXGEN="${_here}/helpers/tf-gen-index.py"

TF_UPSTREAM_BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://storage.googleapis.com/tensorflow"}
BASE_PATH="${TUNASYNC_WORKING_DIR}"

# remove ending slash
BASE_PATH=${BASE_PATH%/}
TF_UPSTREAM_BASE_URL=${TF_UPSTREAM_BASE_URL%/}

failed=0
wget -O - "${TF_UPSTREAM_BASE_URL}/" | ${XMLPARSE} | while read -a tokens; do
	filename=${tokens[0]}
	pkgsize=${tokens[1]}
	
	# Notice: the filename starts with no leading '/'!
	pkgurl="${TF_UPSTREAM_BASE_URL}/${filename}"
	pkgdst="${BASE_PATH}/${filename}"
	pkgdir=`dirname ${pkgdst}`
	mkdir -p ${pkgdir}
	
	declare downloaded=false
	if [[ -f ${pkgdst} ]]; then
		local_size=`stat -c "%s" ${pkgdst}`
		if [ ${local_size} -eq ${pkgsize} ]; then
			downloaded=true
			echo "Skipping ${pkgdst}, size ${pkgsize}"
		fi
	fi
	[[ $downloaded == true ]] && continue

	echo "downloading ${pkgurl} to ${pkgdst}"
	if [[ -z ${DRY_RUN:-} ]]; then
		wget ${WGET_OPTIONS:-} -q -O ${pkgdst} ${pkgurl} || failed=1
	fi
done

find ${BASE_PATH} -type f -name '*.whl' -printf '%P\n' | \
	${INDEXGEN} > "${BASE_PATH}/releases.json"

exit $failed
