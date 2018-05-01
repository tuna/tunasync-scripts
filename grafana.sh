#!/bin/bash
# requires: createrepo reposync wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packagecloud.io/grafana/stable"}

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"

APT_VERSIONS=("wheezy" "jessie" "stretch")
EL_VERSIONS=("6" "7")

mkdir -p ${YUM_PATH} ${APT_PATH}


# =================== APT repos ===============================
if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi
base_url="${BASE_URL}/debian"
for version in ${APT_VERSIONS[@]}; do
	for arch in "amd64" "i386"; do
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

for elver in ${EL_VERSIONS[@]}; do
cat << EOF >> $cfg
[el${elver}]
name=el${elver}
baseurl=${BASE_URL}/el/$elver/x86_64/
enabled=1
EOF
done

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${YUM_PATH} -e $cache_dir
	for elver in ${EL_VERSIONS[@]}; do
		createrepo --update -v -c $cache_dir -o ${YUM_PATH}/el${elver}/ ${YUM_PATH}/el${elver}/
	done
fi
rm $cfg
