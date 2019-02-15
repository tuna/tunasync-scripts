#!/bin/bash
# requires: createrepo reposync wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packages.grafana.com/oss"}

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"

APT_VERSIONS=("stable" "beta")
RPM_VERSIONS=("rpm" "rpm-beta")

mkdir -p ${YUM_PATH} ${APT_PATH}


# =================== APT repos ===============================
if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi
base_url="${BASE_URL}/deb"
for version in "${APT_VERSIONS[@]}"; do
	for arch in "amd64" "arm64" "armhf"; do
		apt-download-binary ${base_url} "$version" "main" "$arch" "${APT_PATH}" || true
	done
done
echo "APT finished"


# =================== YUM/DNF repos ==========================

cache_dir="/tmp/yum-grafana-cache/"
cfg="/tmp/yum-grafana.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0

EOF

for rpmver in "${RPM_VERSIONS[@]}"; do
cat << EOF >> $cfg
[${rpmver}]
name=${rpmver}
baseurl=${BASE_URL}/$rpmver
enabled=1
EOF
done

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${YUM_PATH} -e $cache_dir
	for rpmver in "${RPM_VERSIONS[@]}"; do
		createrepo --update -v -c $cache_dir -o ${YUM_PATH}/${rpmver}/ ${YUM_PATH}/${rpmver}/
	done
fi
rm $cfg
