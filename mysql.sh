#!/bin/bash
# requires: createrepo reposync wget curl rsync
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://repo.mysql.com"}"

MYSQL_DOWNLOAD_PATH="${BASE_PATH}/downloads/"
MYSQL_RSYNC_UPSTREAM="rsync://mysql.he.net/mysql/Downloads/"
RSYNC_OPTS="-aHvh --no-o --no-g --stats --exclude .~tmp~/ --delete --delete-after --delay-updates --safe-links --timeout=120 --contimeout=120"
USE_IPV6=${USE_IPV6:-"0"}
if [[ $USE_IPV6 == "1" ]]; then
	RSYNC_OPTS="-6 ${RSYNC_OPTS}"
fi

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"
UBUNTU_PATH="${APT_PATH}/ubuntu"
DEBIAN_PATH="${APT_PATH}/debian"

UBUNTU_VERSIONS=("trusty" "precise" "xenial")
DEBIAN_VERSIONS=("wheezy" "jessie")


mkdir -p ${YUM_PATH} ${UBUNTU_PATH} ${DEBIAN_PATH}


# =================== APT repos ===============================
if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi
MYSQL_APT_REPOS=("mysql-5.6" "mysql-5.7" "mysql-tools" "connector-python-2.1")
 
base_url="${BASE_URL}/apt/ubuntu"
for version in ${UBUNTU_VERSIONS[@]}; do
	for repo in ${MYSQL_APT_REPOS[@]}; do
		for arch in "amd64" "i386"; do
			apt-download-binary ${base_url} "$version" "$repo" "$arch" "${UBUNTU_PATH}" || true
		done
	done
done
echo "Ubuntu finished"

base_url="${BASE_URL}/apt/debian"
for version in ${DEBIAN_VERSIONS[@]}; do
	for repo in ${MYSQL_APT_REPOS[@]}; do
		for arch in "amd64" "i386"; do
			apt-download-binary ${base_url} "$version" "$repo" "$arch" "${DEBIAN_PATH}" || true
		done
	done
done
echo "Debian finished"


# =================== YUM/DNF repos ==========================

cache_dir="/tmp/yum-mysql-cache/"
cfg="/tmp/yum-mysql.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0

EOF

for elver in "6" "7"; do
cat << EOF >> $cfg 
[mysql-connectors-community-el${elver}]
name=MySQL Connectors Community
baseurl=http://repo.mysql.com/yum/mysql-connectors-community/el/$elver/x86_64/
enabled=1

[mysql-tools-community-el${elver}]
name=MySQL Tools Community
baseurl=http://repo.mysql.com/yum/mysql-tools-community/el/$elver/x86_64/
enabled=1

[mysql56-community-el${elver}]
name=MySQL 5.6 Community Server
baseurl=http://repo.mysql.com/yum/mysql-5.6-community/el/$elver/x86_64/
enabled=1

[mysql57-community-el${elver}]
name=MySQL 5.7 Community Server
baseurl=http://repo.mysql.com/yum/mysql-5.7-community/el/$elver/x86_64/
enabled=1

EOF
done

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${YUM_PATH} -e $cache_dir
	for repo in "mysql-connectors-community" "mysql-tools-community" "mysql56-community" "mysql57-community"; do
		for elver in "6" "7"; do
			createrepo --update -v -c $cache_dir -o ${YUM_PATH}/${repo}-el${elver}/ ${YUM_PATH}/${repo}-el${elver}/
		done
	done
fi
rm $cfg

# --------- dev.mysql.com --------

if [[ -z ${DRY_RUN:-} ]]; then
	rsync ${RSYNC_OPTS} "${MYSQL_RSYNC_UPSTREAM}" "${MYSQL_DOWNLOAD_PATH}"
fi
