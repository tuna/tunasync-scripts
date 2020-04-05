#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://packages.gitlab.com/gitlab/gitlab-ce"}

BASE_PATH="${TUNASYNC_WORKING_DIR}"

YUM_PATH="${BASE_PATH}/yum"

EL_VERSIONS=(6 7 8)
UBUNTU_PATH="${BASE_PATH}/ubuntu/"
DEBIAN_PATH="${BASE_PATH}/debian/"

mkdir -p $UBUNTU_PATH $DEBIAN_PATH $YUM_PATH

cache_dir="/tmp/yum-gitlab-ce-cache/"
cfg="/tmp/gitlab-ce-yum.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0
EOF
for elver in ${EL_VERSIONS[@]}; do
	cat <<EOF >> ${cfg}

[el${elver}]
name=el${elver}
baseurl=${UPSTREAM}/el/${elver}/x86_64
repo_gpgcheck=0
gpgcheck=0
enabled=1
gpgkey=https://packages.gitlab.com/gpg.key
sslverify=0
EOF
done

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${YUM_PATH} -e $cache_dir
	for elver in ${EL_VERSIONS[@]}; do
		createrepo --update -v -c $cache_dir -o ${YUM_PATH}/el${elver} ${YUM_PATH}/el${elver}
	done
fi
rm $cfg

"$apt_sync" "${UPSTREAM}/ubuntu" @ubuntu-lts main amd64,i386 "$UBUNTU_PATH"
echo "Ubuntu finished"
"$apt_sync" "${UPSTREAM}/debian" @debian-current main amd64,i386 "$DEBIAN_PATH"
echo "Debian finished"


# vim: ts=4 sts=4 sw=4
