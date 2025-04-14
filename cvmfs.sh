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

# CERN keeps only maintained versions of CVMFS
ubuntu_os=(noble jammy focal)
debian_os=(bookworm bullseye buster)
deb_suffixes=(prod)
declare -a debian_dists=()
declare -a ubuntu_dists=()

for deb_os in "${debian_os[@]}"; do
   for suffix in "${deb_suffixes[@]}"; do
       debian_dists+=("${deb_os}-${suffix}")
   done
done

for ubuntu_os in "${ubuntu_os[@]}"; do
   for suffix in "${deb_suffixes[@]}"; do
       ubuntu_dists+=("${ubuntu_os}-${suffix}")
   done
done

function join_by { local IFS="$1"; shift; echo "$*"; }
ubuntu_dists_list=$(join_by ',' ${ubuntu_dists[@]})
debian_dists_list=$(join_by ',' ${debian_dists[@]})

echo "All Ubuntu codenames: $ubuntu_dists_list"
echo "All Debian codenames: $debian_dists_list"

# =================== APT repos ===============================
"$apt_sync" --delete "${BASE_URL}/apt" "$ubuntu_dists_list" main amd64,i386,amd64 "$APT_PATH"
echo "Ubuntu finished"
"$apt_sync" --delete "${BASE_URL}/apt" "$debian_dists_list" main amd64,i386,amd64 "$APT_PATH"
echo "Debian finished"

# =================== YUM/DNF repos ==========================
"$yum_sync" "${BASE_URL}/yum/@{comp}/EL/@{os_ver}/@{arch}" 6-9 cvmfs,cvmfs-config,cvmfs-kernel aarch64,i386,ppc64le,x86_64 "@{comp}-EL@{os_ver}-@{arch}" "$YUM_PATH"
echo "YUM finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
