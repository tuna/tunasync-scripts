#!/bin/bash
# requires: lftp wget jq

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"http://images.linuxcontainers.org/"}"

function sync_lxc_images() {
	repo_url="$1"
	repo_dir="$2"

	[ ! -d "$repo_dir" ] && mkdir -p "$repo_dir"
	cd $repo_dir

	lftp "${repo_url}/" -e "mirror --verbose -P 5 --delete --only-newer; bye"
}

sync_lxc_images "${BASE_URL}/images" "${TUNASYNC_WORKING_DIR}/images"

mkdir -p "${TUNASYNC_WORKING_DIR}/meta/1.0"
for i in index-system index-system.asc index-user index-user.asc; do
  wget -O "${TUNASYNC_WORKING_DIR}/meta/1.0/"$i "${BASE_URL}/meta/1.0/"$i
done

mkdir -p "${TUNASYNC_WORKING_DIR}/streams/v1"
wget -O "${TUNASYNC_WORKING_DIR}/streams/v1/index.json" "${BASE_URL}/streams/v1/index.json"

jq -r '.index[].path' "${TUNASYNC_WORKING_DIR}/streams/v1/index.json" | while read line; do
    [ ! -d "${TUNASYNC_WORKING_DIR}/$(dirname $line)" ] && mkdir -p "${TUNASYNC_WORKING_DIR}/$(dirname $line)"
    wget -O "${TUNASYNC_WORKING_DIR}/${line}" "${BASE_URL}/${line}"
done
