#!/bin/bash
# requires: createrepo reposync wget curl rsync
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://repo.mysql.com"}"
MYSQL_RSYNC_UPSTREAM="${DOWNLOADS_RSYNC_UPSTREAM:-rsync://ftp5.gwdg.de/pub/linux/mysql/Downloads/}"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

MYSQL_DOWNLOAD_PATH="${BASE_PATH}/downloads/"
RSYNC_OPTS="-aHv --no-o --no-g --stats --exclude .~tmp~/ --delete --delete-excluded --delete-after --delay-updates --safe-links --timeout=120 --contimeout=120"
USE_IPV6=${USE_IPV6:-"0"}
if [[ $USE_IPV6 == "1" ]]; then
	RSYNC_OPTS="-6 ${RSYNC_OPTS}"
fi

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"
UBUNTU_PATH="${APT_PATH}/ubuntu"
DEBIAN_PATH="${APT_PATH}/debian"

# ================ rsync repo.mysql.com ======================

if [[ -z ${DRY_RUN:-} ]]; then
	logfifo=/tmp/rsync-out.fifo
	mkfifo $logfifo
	awk '/^total size is /{gsub(/,/,"",$4); print "+"$4}' <$logfifo >>"$REPO_SIZE_FILE" &
	rsync ${RSYNC_OPTS} "${MYSQL_RSYNC_UPSTREAM}" "${MYSQL_DOWNLOAD_PATH}" | tee $logfifo
fi

# =================== APT repos ===============================
MYSQL_APT_REPOS="mysql-5.6,mysql-5.7,mysql-tools,connector-python-2.1,mysql-8.0"
"$apt_sync" --delete "${BASE_URL}/apt/ubuntu" trusty,@ubuntu-lts $MYSQL_APT_REPOS amd64,i386 "${UBUNTU_PATH}"
echo "Ubuntu finished"
"$apt_sync" --delete "${BASE_URL}/apt/debian" @debian-current $MYSQL_APT_REPOS amd64,i386 "${DEBIAN_PATH}"
echo "Debian finished"

# =================== YUM/DNF repos ==========================
COMPONENTS="mysql-connectors-community,mysql-tools-community,mysql-8.0-community,mysql-5.6-community,mysql-5.7-community"
"$yum_sync" "${BASE_URL}/yum/@{comp}/el/@{os_ver}/@{arch}/" 6-8 "$COMPONENTS" x86_64,aarch64 "@{comp}-el@{os_ver}-@{arch}" "$YUM_PATH"
echo "YUM finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
