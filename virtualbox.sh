#!/bin/bash
# requires: wget, yum-utils
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)


BASE_PATH="${TUNASYNC_WORKING_DIR}"

RPM_PATH="${BASE_PATH}/rpm"
APT_PATH="${BASE_PATH}/apt"

APT_VERSIONS=("xenial" "trusty" "precise" "stretch" "jessie" "wheezy" "squeeze")
EL_VERSIONS=("5" "6" "7")

mkdir -p ${RPM_PATH} ${APT_PATH}

# === download rhel packages ====
cache_dir="/tmp/yum-virtualbox-el-cache/"
cfg="/tmp/virtualbox-el-yum.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0

EOF

for releasever in ${EL_VERSIONS[@]}; do
cat <<EOF >> ${cfg}
[el${releasever}]
name=Oracle Linux / RHEL / CentOS-5 / x86_64 - VirtualBox
baseurl=http://download.virtualbox.org/virtualbox/rpm/el/$releasever/x86_64
repo_gpgcheck=0
gpgcheck=0
enabled=1
EOF
done

reposync -c $cfg -d -p ${RPM_PATH} -e $cache_dir
for releasever in ${EL_VERSIONS[@]}; do
createrepo --update -v -c $cache_dir -o ${RPM_PATH}/el$releasever ${RPM_PATH}/el$releasever
done
rm $cfg

# === download deb packages ====
base_url="http://download.virtualbox.org/virtualbox/debian"
for version in ${APT_VERSIONS[@]}; do
	apt-download-binary ${base_url} "$version" "contrib" "amd64" "${APT_PATH}" || true
	apt-download-binary ${base_url} "$version" "non-free" "amd64" "${APT_PATH}" || true
	apt-download-binary ${base_url} "$version" "contrib" "i386" "${APT_PATH}" || true
	apt-download-binary ${base_url} "$version" "non-free" "i386" "${APT_PATH}" || true
done
echo "Debian and ubuntu finished"
