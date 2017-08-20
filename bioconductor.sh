#!/bin/bash
# requires: wget, rsync
#

set -e
set -o pipefail

UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"rsync://master.bioconductor.org"}
VERSIONS=("3.5")
RELEASE_VERSION="3.5"

RSYNC_OPTS="-aHvh --no-o --no-g --stats --exclude .~tmp~/ --delete --delete-after --delay-updates --safe-links --timeout=120 --contimeout=120"

USE_IPV6=${USE_IPV6:-"0"}
if [[ $USE_IPV6 == "1" ]]; then
	RSYNC_OPTS="-6 ${RSYNC_OPTS}"
fi

mkdir -p ${TUNASYNC_WORKING_DIR}/packages

for version in ${VERSIONS[@]}; do
	upstream=${UPSTREAM}/${version}
	dest=${TUNASYNC_WORKING_DIR}/packages/${version}

	[ ! -d "$dest" ] && mkdir -p "$dest"
	
	rsync ${RSYNC_OPTS} "$upstream" "$dest"
done

ln -sfT ${RELEASE_VERSION} ${TUNASYNC_WORKING_DIR}/packages/release
