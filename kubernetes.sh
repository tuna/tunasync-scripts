#!/bin/bash
# requires: createrepo reposync wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packages.cloud.google.com"}

YUM_PATH="${BASE_PATH}/yum/repos"
APT_PATH="${BASE_PATH}/apt"

APT_VERSIONS=kubernetes-jessie,kubernetes-stretch,kubernetes-trusty,kubernetes-xenial,minikube-jessie,minikube-trusty
EL_VERSIONS=(kubernetes-el7-aarch64 kubernetes-el7-armhfp kubernetes-el7-x86_64)

mkdir -p ${YUM_PATH} ${APT_PATH}


# =================== APT repos ===============================
"$apt_sync" "${BASE_URL}/apt" $APT_VERSIONS main amd64,i386,armhf,arm64 "$APT_PATH"
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

