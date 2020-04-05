#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://artifacts.elastic.co"}

BASE_PATH="${TUNASYNC_WORKING_DIR%/}"
BASE_URL="${BASE_URL%/}"

ELASTIC_VERSION=("5.x" "6.x" "7.x")

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"

mkdir -p ${YUM_PATH} ${APT_PATH}

# =================== APT repos ===============================

for elsver in "${ELASTIC_VERSION[@]}"; do
	"$apt_sync" "${BASE_URL}/packages/${elsver}/apt" stable main amd64,i386 "${APT_PATH}/${elsver}"
	
	(cd ${BASE_PATH}/${elsver}; ln -sf ../apt/${elsver} apt)
done

# # ================ YUM/DNF repos ===============================

cache_dir="/tmp/yum-elastic-cache/"
cfg="/tmp/yum-elastic.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0

EOF

for elsver in "${ELASTIC_VERSION[@]}"; do
cat <<EOF >> ${cfg}
[elastic-${elsver}]
name=elastic stack ${elsver} packages
baseurl=${BASE_URL}/packages/${elsver}/yum
repo_gpgcheck=0
gpgcheck=0
enabled=1
sslverify=0

EOF
done

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${YUM_PATH} -e ${cache_dir}
	for elsver in ${ELASTIC_VERSION[@]}; do
		createrepo --update -v -c ${cache_dir} -o ${YUM_PATH}/elastic-${elsver}/ ${YUM_PATH}/elastic-${elsver}/
		(cd ${BASE_PATH}/${elsver}; ln -sf ../yum/elastic-${elsver} yum)
	done
fi
rm $cfg
