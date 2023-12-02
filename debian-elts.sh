#!/bin/bash
# requires: debmirror
set -e
set -o pipefail

_here=$(dirname $(realpath $0))
function join { local IFS=","; echo "$*"; }

# standard tunasync env
BASE_PATH="${TUNASYNC_WORKING_DIR}"
APT_URL=${TUNASYNC_UPSTREAM_URL:-"https://deb.freexian.com/extended-lts"}

# parse APT_URL to different parts
proto="$(printf "$APT_URL" | grep :// | sed -e's,^\(.*://\).*,\1,g')"
url="$(printf ${APT_URL/$proto/})"
host="$(printf $url | cut -d/ -f1)"
path="/$(printf $url | grep / | cut -d/ -f2-)"

# override by env if needed
APT_HOST=${DEBMIRROR_HOST:-$host}
APT_PROTO=${DEBMIRROR_PROTO:-$proto}
APT_PATH=${DEBMIRROR_PATH:-$path}
APT_KEYRING_FILE=${DEBMIRROR_APT_KEYRING:-"https://deb.freexian.com/extended-lts/archive-key.gpg"}

# leave all possible values here
# debmirror will only download the intersection of provided options and the repo provides
ARCHES=(amd64 i386 armhf armel arm64)
DIST=(jessie stretch)

# download keyring
keyring_file="/tmp/freexian.$RANDOM.kbx"
wget "$APT_KEYRING_FILE" -O "$keyring_file"

debmirror -a $(join "${ARCHES[@]}") -d $(join "${DIST[@]}") -h "$APT_HOST" -r "$APT_PATH" --method ${APT_PROTO} -v --keyring "$keyring_file" --diff mirror --rsync-extra none --i18n --getcontents "${BASE_PATH}"
