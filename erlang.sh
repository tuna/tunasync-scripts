#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL="https://packages.erlang-solutions.com"

YUM_PATH="${BASE_PATH}/centos"
UBUNTU_PATH="${BASE_PATH}/ubuntu"
DEBIAN_PATH="${BASE_PATH}/debian"

UBUNTU_VERSIONS=("trusty" "xenial" "bionic")
DEBIAN_VERSIONS=("wheezy" "jessie" "stretch")
EL_VERSIONS=("6" "7")

# =================== APT repos ===============================
if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi

base_url="${BASE_URL}/ubuntu"
for version in ${UBUNTU_VERSIONS[@]}; do
	for arch in "amd64" "i386"; do
		apt-download-binary ${base_url} "$version" "contrib" "$arch" "${UBUNTU_PATH}" || true
	done
done
echo "Ubuntu finished"

base_url="${BASE_URL}/debian"
for version in ${DEBIAN_VERSIONS[@]}; do
	for arch in "amd64" "i386"; do
		apt-download-binary ${base_url} "$version" "contrib" "$arch" "${DEBIAN_PATH}" || true
	done
done
echo "Debian finished"

# =================== YUM repos ===============================

cache_dir="/tmp/yum-erlang-cache/"
cfg="/tmp/yum-erlang.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0

EOF

for elver in ${EL_VERSIONS[@]}; do
cat << EOF >> $cfg
[$elver]
name=Elang for el-${elver}
baseurl=${BASE_URL}/rpm/centos/$elver/x86_64
enabled=1
EOF
done

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${YUM_PATH} -e $cache_dir
	for elver in ${EL_VERSIONS[@]}; do
		createrepo --update -v -c $cache_dir -o ${YUM_PATH}/${elver}/ ${YUM_PATH}/${elver}/
	done
fi
rm $cfg
