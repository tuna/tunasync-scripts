#!/bin/bash
# requires: curl, sha256sum, awk, jq
set -e

BASE_PATH="${TUNASYNC_WORKING_DIR}"

# 参数为版本，比如8,11等
function downloadRelease() {
  remote_filelist="$BASE_PATH/$1/filelist"
  mkdir -p "$BASE_PATH/$1"
  echo -n "" >$remote_filelist
  curl -s "https://api.adoptopenjdk.net/v2/latestAssets/releases/openjdk$1" | \
    jq -r '.[]| [.version,.binary_type,.architecture,.os,.binary_name,.binary_link,.checksum_link,.installer_name,.installer_link,.installer_checksum_link]| @tsv' | \
    while IFS=$'\t' read -r version binary_type architecture os binary_name binary_link checksum_link installer_name installer_link installer_checksum_link; do
      mkdir -p "$BASE_PATH/$version/$binary_type/$architecture/$os/" || true
      dest_filename="$BASE_PATH/$version/$binary_type/$architecture/$os/$binary_name"
      echo "$dest_filename" >>$remote_filelist
      echo "$dest_filename.sha256.txt" >>$remote_filelist
      declare downloaded=false
      if [[ -f $dest_filename ]]; then
        echo "Skiping $binary_name"
        downloaded=true
      fi
      local retry=0
      while [[ $retry -lt 3 && $downloaded != true ]]; do
        echo "Downloading ${dest_filename}"
        link="$binary_link"
        download_and_check && {
            downloaded=true
        }
        ((retry+=1))
      done
      if [[ ! -z "$installer_name" ]]; then
        dest_filename="$BASE_PATH/$version/$binary_type/$architecture/$os/$installer_name"
        echo "$dest_filename" >>$remote_filelist
        echo "$dest_filename.sha256.txt" >>$remote_filelist
        downloaded=false
        if [[ -f $dest_filename ]]; then
          echo "Skiping $installer_name"
          downloaded=true
        fi
        retry=0
        while [[ $retry -lt 3 && $downloaded != true ]]; do
          echo "Downloading ${dest_filename}"
          link="$installer_link"
          checksum_link="$installer_checksum_link"
          download_and_check && {
            downloaded=true
          }
          ((retry+=1))
        done
      fi
    done
}

function clean_old_releases() {
  declare version=$1
  declare remote_filelist="$BASE_PATH/$version/filelist"
  declare local_filelist="/tmp/filelist.local"
  [[ ! -f "$remote_filelist" ]] && return 0
  find "$BASE_PATH/$version" -type f > ${local_filelist}
  comm <(sort $remote_filelist) <(sort $local_filelist) -13 | while read file; do
      echo "deleting ${file}"
      # rm "${file}"
  done
}

function download_and_check() {
  rm "${dest_filename}" "${dest_filename}.sha256.txt" 2>/dev/null || true
  rm "${dest_filename}.tmp" "${dest_filename}.sha256.txt.tmp" 2>/dev/null || true
  curl -s -S --fail -L ${CURL_OPTIONS:-}  \
    -o "${dest_filename}.tmp" \
    "$link"
  curl -s -S --fail -L ${CURL_OPTIONS:-}  \
    -o "${dest_filename}.sha256.txt.tmp" \
    "$checksum_link" || {
    echo "Warning: ${dest_filename}.sha256.txt not exist, skipping SHA256 check"
    mv "${dest_filename}.tmp" "${dest_filename}"
    return 0
  }
  sha256sum_check && {
    mv "${dest_filename}.sha256.txt.tmp" "${dest_filename}.sha256.txt"
    mv "${dest_filename}.tmp" "${dest_filename}"
    return 0
  }
}

function sha256sum_check() {
  expected=$(cat "${dest_filename}.sha256.txt.tmp" | awk '{print $1}')
  actual=$(sha256sum "${dest_filename}.tmp" | awk '{print $1}')
  if [[ "$expected" = "$actual" ]]; then
    return 0
  else
    return 1
  fi
}

for i in 8 9 10 11 12 13 14;
do
  downloadRelease $i && clean_old_releases $i
done

