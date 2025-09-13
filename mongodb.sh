#!/bin/bash
set -e

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py"
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"http://repo.mongodb.org"}

MONGO_VERSIONS=("8.0" "7.0" "6.0" "5.0" "4.4" "4.2")
STABLE_VERSION="8.0"

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"
UBUNTU_PATH="${APT_PATH}/ubuntu"
DEBIAN_PATH="${APT_PATH}/debian"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

components=$(printf ",%s" "${MONGO_VERSIONS[@]}")
components=${components:1}
"$yum_sync" "${BASE_URL}/yum/redhat/@{os_ver}/mongodb-org/@{comp}/@{arch}/" @rhel-current "$components" x86_64 "el@{os_ver}-@{comp}" "$YUM_PATH"
pushd "${YUM_PATH}"
for stable in el*-${STABLE_VERSION}; do
	# e.g. "el8" -> "el8-4.2"
	ln -fsn $stable ${stable%-$STABLE_VERSION}
done
popd
echo "YUM finished"

components=$(printf ",@{ubuntu-lts}/mongodb-org/%s" "${MONGO_VERSIONS[@]}")
"$apt_sync" --delete "$BASE_URL/apt/ubuntu" "${components:1}" multiverse amd64,i386,arm64 "$UBUNTU_PATH"
components=$(printf ",@{debian-current}/mongodb-org/%s" "${MONGO_VERSIONS[@]}")
"$apt_sync" --delete "$BASE_URL/apt/debian" "${components:1}" main amd64,i386 "$DEBIAN_PATH"

for dist in "$BASE_URL"/apt/*/dists/*/mongodb-org/; do
	stable=${STABLE_VERSION}
	if [[ $dist == *"trusty"* ||  $dist == *"jessie"* ]]; then
		# 4.2 not provided for the oldoldstable
		stable=4.0
	fi
	[[ -e "${dist}/${stable}" ]] && (cd "${dist}" && ln -fsn "${stable}" stable)
done
echo "APT finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm

# vim: ts=4 sts=4 sw=4
