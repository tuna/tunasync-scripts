#!/bin/bash 
# requires: wget, lftp, jq, python3.5, lxml, pyquery 
set -e 
set -u 
set -o pipefail

_here=`dirname $(realpath $0)`
HTMLPARSE="${_here}/helpers/anaconda-filelist.py"

DEFAULT_CONDA_REPO_BASE="https://repo.continuum.io"
DEFAULT_CONDA_CLOUD_BASE="https://conda.anaconda.org"

CONDA_REPO_BASE="${CONDA_REPO_BASE:-$DEFAULT_CONDA_REPO_BASE}"
CONDA_CLOUD_BASE="${CONDA_CLOUD_BASE:-$DEFAULT_CONDA_CLOUD_BASE}"

LOCAL_DIR_BASE="${TUNASYNC_WORKING_DIR}"

TMP_DIR=$(mktemp -d)

CONDA_REPOS=("free" "r" "mro" "pro")
CONDA_ARCHES=("noarch" "linux-64" "linux-32" "linux-armv6l" "linux-armv7l" "linux-ppc64le" "osx-64" "osx-32" "win-64" "win-32")

CONDA_CLOUD_REPOS=("conda-forge/linux-64" "conda-forge/osx-64" "conda-forge/win-64" "conda-forge/noarch" "msys2/win-64" "msys2/noarch")

EXIT_STATUS=0
EXIT_MSG=""

function check-and-download () {
	remote_file=$1
	local_file=$2
	wget -q --spider ${remote_file}
	if [ $? -eq 0 ]; then
		echo "downloading ${remote_file}"
		wget -q -N -O ${local_file} ${remote_file}
		return
	fi
	return 1
}

function cleanup () {
	echo "cleaning up"
	[[ -d ${TMP_DIR} ]] && {
		[[ -f ${TMP_DIR}/repodata.json ]] && rm ${TMP_DIR}/repodata.json
		[[ -f ${TMP_DIR}/repodata.json.bz2 ]] && rm ${TMP_DIR}/repodata.json.bz2
		[[ -f ${TMP_DIR}/failed ]] && rm ${TMP_DIR}/failed
		rmdir ${TMP_DIR}
	}
}

function download-with-checksum () {
	local pkg_url=$1
	local dest_file=$2
	local pkgmd5=$3

	local declare downloaded=false
	local trials=0

	while [[ $downloaded != true ]]; do
		echo "downloading ${pkg_url}"
		wget -q -O ${dest_file} ${pkg_url} && {
			# two space for md5sum check format
			{ md5sum -c - < <(echo "${pkgmd5} ${dest_file}"); } && downloaded=true || trials=$((trials + 1))
		} || {
			trials=$((trials + 1))
		}
		if (( $trials > 3 )); then
			return 1
		fi
	done
	return 0
}

trap cleanup EXIT


function sync_installer () {
	repo_url="$1"
	repo_dir="$2"

	[[ ! -d "$repo_dir" ]] && mkdir -p "$repo_dir"
	cd $repo_dir
	
	while read -a tokens; do
		fname=${tokens[0]}
		pkgmd5=${tokens[2]}

		dest_file="${repo_dir}${fname}"
		pkg_url="${repo_url}${fname}"
		pkgsize=`curl --head -s ${pkg_url} | grep 'Content-Length' | awk '{print $2}' | tr -d '\r'`
		
		if [[ -f ${dest_file} ]]; then
			rsize=`stat -c "%s" ${dest_file}`
			if (( ${rsize} == ${pkgsize} )); then
				echo "Skipping ${fname}, size ${pkgsize}"
				continue
			fi
		fi
		download-with-checksum ${pkg_url} ${dest_file} ${pkgmd5} || {
			echo "Failed to download ${pkg_url}: checksum mismatch"
			echo ${pkg_url} >> ${TMP_DIR}/failed
			EXIT_STATUS=2
			EXIT_MSG="some files has bad checksum."
		}
	done < <(wget -O- ${repo_url} | $HTMLPARSE)
}

function sync_repo () {
	local repo_url="$1"
	local local_dir="$2"
	
	[[ ! -d ${local_dir} ]] && mkdir -p ${local_dir}
	
	repodata_url="${repo_url}/repodata.json"
	bz2_repodata_url="${repo_url}/repodata.json.bz2"

	tmp_repodata="${TMP_DIR}/repodata.json"
	tmp_bz2_repodata="${TMP_DIR}/repodata.json.bz2"

	check-and-download ${repodata_url} ${tmp_repodata}
	check-and-download ${bz2_repodata_url} ${tmp_bz2_repodata}

	jq_cmd='.packages | to_entries[] | [.key, .value.size, .value.md5] | map(tostring) | join(" ")'

	while read line; do
		read -a tokens <<< $line
		pkgfile=${tokens[0]}
		pkgsize=${tokens[1]}
		pkgmd5=${tokens[2]}
		
		pkg_url="${repo_url}/${pkgfile}"
		dest_file="${local_dir}/${pkgfile}"
		
		if [[ -f ${dest_file} ]]; then
			rsize=`stat -c "%s" ${dest_file}`
			if (( ${rsize} == ${pkgsize} )); then
				echo "Skipping ${pkgfile}, size ${pkgsize}"
				continue
			fi
		fi

		download-with-checksum ${pkg_url} ${dest_file} ${pkgmd5} || {
			echo "Failed to download ${pkg_url}: checksum mismatch"
			echo ${pkg_url} >> ${TMP_DIR}/failed
			EXIT_MSG="some files has bad checksum."
		}

	done < <(bzip2 -c -d ${tmp_bz2_repodata} | jq -r "${jq_cmd}")
	
	mv -f "${TMP_DIR}/repodata.json" "${local_dir}/repodata.json"
	mv -f "${TMP_DIR}/repodata.json.bz2" "${local_dir}/repodata.json.bz2"
}

sync_installer "${CONDA_REPO_BASE}/archive/" "${LOCAL_DIR_BASE}/archive/"
sync_installer "${CONDA_REPO_BASE}/miniconda/" "${LOCAL_DIR_BASE}/miniconda/"

for repo in ${CONDA_REPOS[@]}; do
	for arch in ${CONDA_ARCHES[@]}; do
		remote_url="${CONDA_REPO_BASE}/pkgs/$repo/$arch"
		local_dir="${LOCAL_DIR_BASE}/pkgs/$repo/$arch"

		sync_repo "${remote_url}" "${local_dir}" || true
	done
done

for repo in ${CONDA_CLOUD_REPOS[@]}; do
	remote_url="${CONDA_CLOUD_BASE}/${repo}"
	local_dir="${LOCAL_DIR_BASE}/cloud/${repo}"

	sync_repo "${remote_url}" "${local_dir}" || true
done


[[ -f ${TMP_DIR}/failed ]] && {
	echo "failed to download following packages:"
	cat ${TMP_DIR}/failed
	mv ${TMP_DIR}/failed ${LOCAL_DIR_BASE}/failed_packages.txt
}

[[ -z $EXIT_MSG ]] || echo $EXIT_MSG
exit $EXIT_STATUS
