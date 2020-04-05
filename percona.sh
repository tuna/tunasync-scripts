#!/bin/bash
# requires: createrepo reposync wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
alias apt-sync="${_here}/apt-sync.py" 

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://repo.percona.com"}

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"

EL_VERSIONS=("6" "7")

# =================== APT repos ===============================
apt-sync "${BASE_URL}/apt" @debian-current,@ubuntu-lts main amd64,i386 "${APT_PATH}"
echo "APT finished"

# =================== YUM/DNF repos ==========================
mkdir -p ${YUM_PATH}

cache_dir="/tmp/yum-percona-cache/"
cfg="/tmp/yum-percona.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0

EOF

for elver in ${EL_VERSIONS[@]}; do
cat << EOF >> $cfg
[el${elver}]
name=el${elver}
baseurl=${BASE_URL}/centos/$elver/os/x86_64/
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
