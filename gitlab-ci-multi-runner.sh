#!/bin/bash
# reqires: wget, yum-utils
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

BASE_PATH="${TUNASYNC_WORKING_DIR}"
UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://packages.gitlab.com/runner/gitlab-ci-multi-runner"}

YUM_PATH="${BASE_PATH}/yum"
UBUNTU_PATH="${BASE_PATH}/ubuntu/"
DEBIAN_PATH="${BASE_PATH}/debian/"

mkdir -p $UBUNTU_PATH $DEBIAN_PATH $YUM_PATH

cache_dir="/tmp/yum-gitlab-runner-cache/"
cfg="/tmp/gitlab-runner-yum.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0

[el6]
name=gitlab-ci-multi-runner-el6
baseurl=https://packages.gitlab.com/runner/gitlab-ci-multi-runner/el/6/x86_64
repo_gpgcheck=0
gpgcheck=0
enabled=1
gpgkey=https://packages.gitlab.com/gpg.key
sslverify=0

[el7]
name=gitlab-ci-multi-runner-el7
baseurl=https://packages.gitlab.com/runner/gitlab-ci-multi-runner/el/7/x86_64
repo_gpgcheck=0
gpgcheck=0
enabled=1
gpgkey=https://packages.gitlab.com/gpg.key
sslverify=0
EOF

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${YUM_PATH}  -e $cache_dir
	[ ! -d ${YUM_PATH}/el6 ] && mkdir -p ${YUM_PATH}/el6
	[ ! -d ${YUM_PATH}/el7 ] && mkdir -p ${YUM_PATH}/el7
	createrepo --update -v -c $cache_dir -o ${YUM_PATH}/el6 ${YUM_PATH}/el6
	createrepo --update -v -c $cache_dir -o ${YUM_PATH}/el7 ${YUM_PATH}/el7
fi
rm $cfg


"$apt_sync" "${UPSTREAM}/ubuntu" @ubuntu-lts main amd64,i386 "$UBUNTU_PATH"
echo "Ubuntu finished"
"$apt_sync" "${UPSTREAM}/debian" @debian-current main amd64,i386 "$DEBIAN_PATH"
echo "Debian finished"


# vim: ts=4 sts=4 sw=4
