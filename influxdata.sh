#!/bin/bash
# requires: createrepo reposync wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://repos.influxdata.com"}

YUM_PATH="${BASE_PATH}/yum"
UBUNTU_PATH="${BASE_PATH}/ubuntu"
DEBIAN_PATH="${BASE_PATH}/debian"

EL_VERSIONS=("6" "7" "8")

mkdir -p ${YUM_PATH} ${UBUNTU_PATH} ${DEBIAN_PATH}

wget -O ${BASE_PATH}/influxdb.key ${BASE_URL}/influxdb.key

# =================== APT repos ===============================

"$apt_sync" "${BASE_URL}/ubuntu" @ubuntu-lts stable amd64,i386,armhf,arm64 "$UBUNTU_PATH"
echo "Ubuntu finished"
"$apt_sync" "${BASE_URL}/debian" @debian-current stable amd64,i386,armhf,arm64 "$DEBIAN_PATH"
echo "Debian finished"


# =================== YUM/DNF repos ==========================

cache_dir="/tmp/yum-influxdata-cache/"
cfg="/tmp/yum-influxdata.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0

EOF

for elver in ${EL_VERSIONS[@]}; do
cat << EOF >> $cfg
[el${elver}-x86_64]
name=el${elver}
baseurl=${BASE_URL}/rhel/$elver/x86_64/stable/
enabled=1
EOF
done

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${YUM_PATH} -e $cache_dir
	for elver in ${EL_VERSIONS[@]}; do
		createrepo --update -v -c $cache_dir -o ${YUM_PATH}/el${elver}-x86_64/ ${YUM_PATH}/el${elver}-x86_64/
	done
fi
rm $cfg
