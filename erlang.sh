#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL="https://packages.erlang-solutions.com"

YUM_PATH="${BASE_PATH}/centos"
UBUNTU_PATH="${BASE_PATH}/ubuntu"
DEBIAN_PATH="${BASE_PATH}/debian"

EL_VERSIONS=("6" "7" "8")

# =================== APT repos ===============================
"$apt_sync" "${BASE_URL}/ubuntu" @ubuntu-lts contrib amd64,i386 "$UBUNTU_PATH"
echo "Ubuntu finished"
"$apt_sync" "${BASE_URL}/debian" @debian-current contrib amd64,i386 "$DEBIAN_PATH"
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
