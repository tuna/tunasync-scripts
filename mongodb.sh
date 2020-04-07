#!/bin/bash
set -e

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"http://repo.mongodb.org"}

MONGO_VERSIONS=("4.2" "4.0" "3.6")
STABLE_VERSION="4.2"

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"
UBUNTU_PATH="${APT_PATH}/ubuntu"
DEBIAN_PATH="${APT_PATH}/debian"

components=$(printf ",%s" "${MONGO_VERSIONS[@]}")
components=${components:1}
"$yum_sync" "${BASE_URL}/yum/redhat/@{os_ver}/mongodb-org/@{comp}/@{arch}/" 6-8 "$components" x86_64 "el@{os_ver}-@{comp}" "$YUM_PATH"
pushd "${YUM_PATH}"
for stable in el*-${STABLE_VERSION}; do
	# e.g. "el8" -> "el8-4.2"
	ln -fsn $stable ${stable%-$STABLE_VERSION}
done
popd
echo "YUM finished"

for mgver in ${MONGO_VERSIONS[@]}; do
	"$apt_sync" "$BASE_URL/apt/ubuntu" "@{ubuntu-lts}/mongodb-org/$mgver" multiverse amd64,i386 "$UBUNTU_PATH"
	"$apt_sync" "$BASE_URL/apt/debian" "@{debian-current}/mongodb-org/$mgver" main amd64,i386 "$DEBIAN_PATH"
done
for dist in "$BASE_URL"/apt/*/dists/*/mongodb-org/; do
	stable=${STABLE_VERSION}
	if [[ $dist == *"trusty"* ||  $dist == *"jessie"* ]]; then
		# 4.2 not provided for the oldoldstable
		stable=4.0
	fi
	[[ -e "${dist}/${stable}" ]] && (cd "${dist}" && ln -fsn "${stable}" stable)
done
echo "APT finished"


# vim: ts=4 sts=4 sw=4
