#!/bin/bash
# requires: wget, timeout, sha256sum, awk
set -e

BASE_PATH="${TUNASYNC_WORKING_DIR}"

# 参数为版本，比如8,11等
function downloadRelease() {
  curl -s "https://api.adoptopenjdk.net/v2/latestAssets/releases/openjdk$1" | \
    jq -r '.[]| [.version,.binary_type,.architecture,.os,.binary_name,.binary_link,.checksum_link]| @tsv' | \
    while IFS=$'\t' read -r version binary_type architecture os binary_name binary_link checksum_link; do
      mkdir -p "$BASE_PATH/$version/$binary_type/$architecture/$os/" || true
      dest_filename="$BASE_PATH/$version/$binary_type/$architecture/$os/$binary_name"
      declare downloaded=false
      if [[ -f $dest_filename ]]; then
        sha256sum_check && {
          downloaded=true
          echo "Skiping $binary_name"
        }
      fi
      while [[ $downloaded != true ]]; do
		echo "Downloading ${dest_filename}"
        rm ${dest_filename} ${dest_filename}.sha256.txt 2>/dev/null || true
        wget -t 2 -T 30 ${WGET_OPTIONS:-}  \
          -O "${dest_filename}" \
          "$binary_link"
        wget -t 2 -T 30 ${WGET_OPTIONS:-}  \
          -O "${dest_filename}.sha256.txt" \
          "$checksum_link"
        sha256sum_check && {
          downloaded=true
        }
      done
    done
}

function sha256sum_check() {
  expected=$(cat "${dest_filename}.sha256.txt" | awk '{print $1}')
  actual=$(sha256sum "${dest_filename}" | awk '{print $1}')
  if [ "$expected" = "$actual" ]; then
    return 0
  else
    return 1
  fi
}

for i in 8 11 13;
do
  downloadRelease $i
done

