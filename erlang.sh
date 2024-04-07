#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL="${TUNASYNC_UPSTREAM_URL}"

CENTOS_PATH="${BASE_PATH}/centos"
UBUNTU_PATH="${BASE_PATH}/ubuntu"
DEBIAN_PATH="${BASE_PATH}/debian"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

# generate codenames for repos
ubuntu_os=(bionic focal jammy)
debian_os=(bullseye buster)
deb_suffixes=(
    mongooseim-5
    mongooseim-6
    esl-erlang-24
    esl-erlang-25
    esl-erlang-26
    elixir-1.12
    elixir-1.13
    elixir-1.14
    elixir-1.15
)

function join_by { local IFS="$1"; shift; echo "$*"; }
ubuntu_codenames=$(join_by ',' $(IFS=','; eval echo {"${ubuntu_os[*]}"}-{"${deb_suffixes[*]}"}))
debian_codenames=$(join_by ',' $(IFS=','; eval echo {"${debian_os[*]}"}-{"${deb_suffixes[*]}"}))

# =================== APT repos ===============================

"$apt_sync" --delete "${BASE_URL}/ubuntu" "$ubuntu_codenames" contrib amd64,arm64 "$UBUNTU_PATH"
echo "Ubuntu finished"
"$apt_sync" --delete "${BASE_URL}/debian" "$debian_codenames" contrib amd64,arm64 "$DEBIAN_PATH"
echo "Debian finished"

# =================== YUM repos ===============================
## DISABLED due to invalid repo structure

# "$yum_sync" "${BASE_URL}/centos/@{os_ver}/@{arch}" 7 erlang x86_64 "@{os_ver}" "$CENTOS_PATH"
# echo "CentOS finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
