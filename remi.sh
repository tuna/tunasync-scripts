#!/bin/bash
# requires: wget, rsync
#

set -e
set -o pipefail

UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"rsync://rpms.remirepo.net"}
REPOS=("enterprise" "fedora")

RSYNC_OPTS="-aHvh --no-o --no-g --stats --exclude .~tmp~/ --delete --delete-after --delay-updates --safe-links --timeout=120 --contimeout=120"

USE_IPV6=${USE_IPV6:-"0"}
if [[ $USE_IPV6 == "1" ]]; then
	RSYNC_OPTS="-6 ${RSYNC_OPTS}"
fi


for repo in ${REPOS[@]}; do
	upstream=${UPSTREAM}/${repo}
	dest=${TUNASYNC_WORKING_DIR}/${repo}

	[ ! -d "$dest" ] && mkdir -p "$dest"
	
	rsync ${RSYNC_OPTS} "$upstream" "$dest"
done

wget -O ${TUNASYNC_WORKING_DIR}/index.html http://rpms.remirepo.net/index.html
wget -O ${TUNASYNC_WORKING_DIR}/PRM-GPG-KEY-remi http://rpms.remirepo.net/RPM-GPG-KEY-remi
