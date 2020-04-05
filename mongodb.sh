#!/bin/bash
set -e

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"http://repo.mongodb.org"}

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"

RHEL_VERSIONS=("6" "7" "8")
MONGO_VERSIONS=("4.2" "4.0" "3.6")
STABLE_VERSION="4.2"

UBUNTU_PATH="${APT_PATH}/ubuntu"
DEBIAN_PATH="${APT_PATH}/debian"

mkdir -p $UBUNTU_PATH $DEBIAN_PATH $YUM_PATH

cache_dir="/tmp/yum-mongodb-cache/"
cfg="/tmp/mongodb-yum.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0

EOF

for mgver in ${MONGO_VERSIONS[@]}; do
	for elver in ${RHEL_VERSIONS[@]}; do
		# Check if mongo/os version combination exists
		wget -q --spider "https://repo.mongodb.org/yum/redhat/$elver/mongodb-org/$mgver/" \
		&& cat <<EOF >> ${cfg}
[el$elver-${mgver}]
name=el$elver-${mgver}
baseurl=https://repo.mongodb.org/yum/redhat/$elver/mongodb-org/${mgver}/x86_64/
repo_gpgcheck=0
gpgcheck=0
enabled=1
sslverify=0

EOF
	done
done

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${YUM_PATH} -e $cache_dir
	for mgver in ${MONGO_VERSIONS[@]}; do
		for elver in ${RHEL_VERSIONS[@]}; do
			[[ -e "${YUM_PATH}/el$elver-$mgver/" ]] && createrepo --update -v -c $cache_dir -o "${YUM_PATH}/el$elver-$mgver/" "${YUM_PATH}/el$elver-$mgver/"
		done
	done
fi

for elver in ${RHEL_VERSIONS[@]}; do
	[[ -e "${YUM_PATH}/el$elver-${STABLE_VERSION}" ]] && (cd "${YUM_PATH}" && ln -fs "el$elver-${STABLE_VERSION}" el$elver)
done

rm $cfg


if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi

base_url="http://repo.mongodb.org"
for mgver in ${MONGO_VERSIONS[@]}; do
	"$apt_sync" "$BASE_URL/apt/ubuntu" "@{ubuntu-lts}/mongodb-org/$mgver" multiverse amd64,i386 "$UBUNTU_PATH"
	"$apt_sync" "$BASE_URL/apt/debian" "@{debian-current}/mongodb-org/$mgver" main amd64,i386 "$DEBIAN_PATH"
done
for dist in "$BASE_URL"/apt/*/dists/*/mongodb-org/; do
	[[ -e "${dist}/${STABLE_VERSION}" ]] && (cd "${dist}" && ln -fs "${STABLE_VERSION}" stable)
done
echo "APT finished"


# vim: ts=4 sts=4 sw=4
