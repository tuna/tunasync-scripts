#!/bin/bash
set -e

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

BASE_PATH="${TUNASYNC_WORKING_DIR}"

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"

RHEL_VERSIONS=("6" "7" "8")
UBUNTU_VERSIONS=("trusty" "precise" "xenial" "bionic")
DEBIAN_VERSIONS=("wheezy" "jessie" "stretch" "buster")
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
	[[ -e "${YUM_PATH}/el$elver" ]] || (cd "${YUM_PATH}" && ln -fs "el$elver-${STABLE_VERSION}" el$elver)
done

rm $cfg


if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi

base_url="http://repo.mongodb.org/apt/ubuntu"
for ubver in ${UBUNTU_VERSIONS[@]}; do
	for mgver in ${MONGO_VERSIONS[@]}; do
		version="$ubver/mongodb-org/$mgver"
		apt-download-binary ${base_url} "$version" "multiverse" "amd64" "${UBUNTU_PATH}" || true
		apt-download-binary ${base_url} "$version" "multiverse" "i386" "${UBUNTU_PATH}" || true
	done
	mg_basepath="${UBUNTU_PATH}/dists/$ubver/mongodb-org"
	[ -e ${mg_basepath}/stable ] || (cd ${mg_basepath}; ln -s ${STABLE_VERSION} stable)
done
echo "Ubuntu finished"

base_url="http://repo.mongodb.org/apt/debian"
for dbver in ${DEBIAN_VERSIONS[@]}; do
	for mgver in ${MONGO_VERSIONS[@]}; do
		version="$dbver/mongodb-org/$mgver"
		apt-download-binary ${base_url} "$version" "main" "amd64" "${DEBIAN_PATH}" || true
		apt-download-binary ${base_url} "$version" "main" "i386" "${DEBIAN_PATH}" || true
	done
	mg_basepath="${DEBIAN_PATH}/dists/$dbver/mongodb-org"
	[ -e ${mg_basepath}/stable ] || (cd ${mg_basepath}; ln -s ${STABLE_VERSION} stable)
done
echo "Debian finished"


# vim: ts=4 sts=4 sw=4
