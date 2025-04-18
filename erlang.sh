#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packages.erlang-solutions.com"}

CENTOS_PATH="${BASE_PATH}/centos"
UBUNTU_PATH="${BASE_PATH}/ubuntu"
DEBIAN_PATH="${BASE_PATH}/debian"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

# generate codenames for repos
ubuntu_os=(jammy noble)
debian_os=(bullseye bookworm)
deb_suffixes=(
    mongooseim-5
    mongooseim-6
    esl-erlang-24
    esl-erlang-25
    esl-erlang-26
    esl-erlang-27
    elixir-1.14
    elixir-1.15
    elixir-1.16
    elixir-1.17
    elixir-1.18
)
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

"$apt_sync" --delete "${BASE_URL}/ubuntu" "$ubuntu_dists_list" contrib amd64,arm64 "$UBUNTU_PATH"
echo "Ubuntu finished"
"$apt_sync" --delete "${BASE_URL}/debian" "$debian_dists_list" contrib amd64,arm64 "$DEBIAN_PATH"
echo "Debian finished"

# =================== YUM repos ===============================
## DISABLED due to invalid repo structure

# "$yum_sync" "${BASE_URL}/centos/@{os_ver}/@{arch}" 7 erlang x86_64 "@{os_ver}" "$CENTOS_PATH"
# echo "CentOS finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
