#!/bin/bash
# requires: createrepo reposync wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packages.cloud.google.com"}

YUM_PATH="${BASE_PATH}/yum/repos"
APT_PATH="${BASE_PATH}/apt"

APT_VERSIONS=(kubernetes-jessie kubernetes-stretch kubernetes-trusty kubernetes-xenial minikube-jessie minikube-trusty)
EL_VERSIONS=(kubernetes-el7-aarch64 kubernetes-el7-armhfp kubernetes-el7-x86_64)

mkdir -p ${YUM_PATH} ${APT_PATH}


# =================== APT repos ===============================
if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi
base_url="${BASE_URL}/apt"
for version in ${APT_VERSIONS[@]}; do
	for arch in "amd64" "i386" "arm64" "armhf"; do
		echo "=== Syncing $version $arch"
		apt-download-binary ${base_url} "$version" "main" "$arch" "${APT_PATH}" || true
	done
done
echo "APT finished"

# =================== YUM/DNF repos ==========================

base_url="${BASE_URL}/yum/repos"
cache_dir="/tmp/yum-k8s-cache/"
cfg="/tmp/yum-k8s.conf"


if [[ -z ${DRY_RUN:-} ]]; then

	for elver in ${EL_VERSIONS[@]}; do

		echo "=== Syncing $elver"
		cat << EOF > $cfg
[main]
keepcache=0
[${elver}]
name=${elver}
baseurl=${base_url}/${elver}/
enabled=1
EOF
		arch=(${elver//-/ })
		arch=${arch[-1]}
		reposync -a "$arch" -c "$cfg" -d -p "${YUM_PATH}" -e "$cache_dir"
		[[ -d "${YUM_PATH}/${elver}" ]] || mkdir "${YUM_PATH}/${elver}"
		createrepo --update -v -c "$cache_dir" -o "${YUM_PATH}/${elver}/" "${YUM_PATH}/${elver}/"
	done
fi

