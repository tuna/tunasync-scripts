#!/bin/bash
# requires: createrepo reposync wget curl
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://cvmrepo.s3-website.cern.ch/cvmrepo"}"

APT_PATH="${BASE_PATH}/apt"
YUM_PATH="${BASE_PATH}/yum"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

# =================== APT repos ===============================
"$apt_sync" --delete "${BASE_URL}/apt" bionic-prod,bookworm-prod,bullseye-prod,buster-prod,focal-prod,jammy-prod,jessie-prod,noble-prod,precise-prod,stable,stretch-prod,trusty-prod,xenial-prod main i386,amd64 "$APT_PATH"
echo "APT finished"

# =================== YUM/DNF repos ==========================
"$yum_sync" "${BASE_URL}/yum/@{comp}/EL/@{os_ver}/@{arch}" 6-9 cvmfs,cvmfs-config,cvmfs-kernel aarch64,i386,ppc64le,x86_64 "@{comp}-EL@{os_ver}-@{arch}" "$YUM_PATH"
echo "YUM finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
