#!/bin/bash
# requires: lftp wget jq
set -e
set -o pipefail

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"http://images.linuxcontainers.org"}"

function sync_lxc_images() {
	repo_url="$1"
	repo_dir="$2"

	[[ ! -d "$repo_dir" ]] && mkdir -p "$repo_dir"
	cd "$repo_dir"

	lftp "${repo_url}" -e "mirror --verbose -P 5 --delete --only-newer; bye"
	echo "lftp returns $?"
}


echo "=== Downloading /meta/1.0 ==="
mkdir -p "${TUNASYNC_WORKING_DIR}/meta/1.0"
for i in index-system index-system.asc index-user index-user.asc; do
  wget -O "${TUNASYNC_WORKING_DIR}/meta/1.0/$i.work-in-progress" "${BASE_URL}/meta/1.0/$i"
done

echo "=== Downloading /streams/v1 ==="
mkdir -p "${TUNASYNC_WORKING_DIR}/streams/v1"
wget -O "${TUNASYNC_WORKING_DIR}/streams/v1/index.json.work-in-progress" "${BASE_URL}/streams/v1/index.json"

jq -r '.index[].path' "${TUNASYNC_WORKING_DIR}/streams/v1/index.json.work-in-progress" | while read line; do
    [[ ! -d "${TUNASYNC_WORKING_DIR}/$(dirname $line)" ]] && mkdir -p "${TUNASYNC_WORKING_DIR}/$(dirname $line)"
    wget -O "${TUNASYNC_WORKING_DIR}/${line}.work-in-progress" "${BASE_URL}/${line}"
done

echo "=== Downloading images ==="

images_json="${TUNASYNC_WORKING_DIR}/streams/v1/images.json.work-in-progress"
[[ -f "$images_json" ]] || exit 1
jq -r '.products[].versions[].items[].path' "$images_json" > /tmp/filelist.txt

#cut -f 6 -d ';' "${TUNASYNC_WORKING_DIR}/meta/1.0/index-system.work-in-progress"
cat /tmp/filelist.txt | while read line; do
    # $line looks like 'images/ubuntu/xenial/armhf/default/20200219_07:42/rootfs.tar.xz'
    dir="$(dirname $line)"
    if [[ "$dir" = "$last_dir" ]]; then
        continue
    fi
    last_dir="$dir"
    echo "=== Syncing $dir ==="
    sync_lxc_images "${BASE_URL}/${dir}" "${TUNASYNC_WORKING_DIR}/${dir}"
done

echo "=== Replacing /meta/1.0 ==="
for i in index-system index-system.asc index-user index-user.asc; do
  mv -f "${TUNASYNC_WORKING_DIR}/meta/1.0/$i.work-in-progress" "${TUNASYNC_WORKING_DIR}/meta/1.0/$i"
done

echo "=== Replacing /streams/v1 ==="
jq -r '.index[].path' "${TUNASYNC_WORKING_DIR}/streams/v1/index.json.work-in-progress" | while read line; do
    mv -f "${TUNASYNC_WORKING_DIR}/${line}.work-in-progress" "${TUNASYNC_WORKING_DIR}/${line}"
done
mv -f "${TUNASYNC_WORKING_DIR}/streams/v1/index.json.work-in-progress" "${TUNASYNC_WORKING_DIR}/streams/v1/index.json"

echo "=== Removing old images ==="

cd "${TUNASYNC_WORKING_DIR}"

find images/ -maxdepth 5 -mindepth 5 -mtime +3 | while read line; do
    # $line looks like 'images/ubuntu/xenial/armhf/default/20200217_07:42'
    grep --quiet "$line" /tmp/filelist.txt || ( echo "Removing $line"; rm -rf "$line" )
done
