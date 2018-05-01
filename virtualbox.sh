#!/bin/bash
# requires: wget, yum-utils, timeout, md5sum
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[[ -z "${LOADED_APT_DOWNLOAD}" ]] && { echo "failed to load apt-download"; exit 1; }


BASE_URL="http://download.virtualbox.org/virtualbox"
BASE_PATH="${TUNASYNC_WORKING_DIR}"

RPM_PATH="${BASE_PATH}/rpm"
APT_PATH="${BASE_PATH}/apt"

APT_VERSIONS=("xenial" "trusty" "precise" "stretch" "jessie" "wheezy" "squeeze" "bionic")
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
baseurl=${BASE_URL}/rpm/el/$releasever/x86_64
repo_gpgcheck=0
gpgcheck=0
enabled=1
EOF
done

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${RPM_PATH} -e $cache_dir
	for releasever in ${EL_VERSIONS[@]}; do
		createrepo --update -v -c $cache_dir -o ${RPM_PATH}/el$releasever ${RPM_PATH}/el$releasever
	done
fi
rm $cfg

# === download deb packages ====
if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi

for version in ${APT_VERSIONS[@]}; do
	apt-download-binary "${BASE_URL}/debian" "$version" "contrib" "amd64" "${APT_PATH}" || true
	apt-download-binary "${BASE_URL}/debian" "$version" "non-free" "amd64" "${APT_PATH}" || true
	apt-download-binary "${BASE_URL}/debian" "$version" "contrib" "i386" "${APT_PATH}" || true
	apt-download-binary "${BASE_URL}/debian" "$version" "non-free" "i386" "${APT_PATH}" || true
done
echo "Debian and ubuntu finished"

# === download standalone packages ====

timeout -s INT 300 wget ${WGET_OPTIONS:-} -q -O "${BASE_PATH}/LATEST.TXT" "${BASE_URL}/LATEST.TXT"
LATEST_VERSION=`cat "${BASE_PATH}/LATEST.TXT"`
LATEST_PATH="${BASE_PATH}/${LATEST_VERSION}"

mkdir -p ${LATEST_PATH}
timeout -s INT 300 wget ${WGET_OPTIONS:-} -q -O "${LATEST_PATH}/MD5SUMS" "${BASE_URL}/${LATEST_VERSION}/MD5SUMS"
timeout -s INT 300 wget ${WGET_OPTIONS:-} -q -O "${LATEST_PATH}/SHA256SUMS" "${BASE_URL}/${LATEST_VERSION}/SHA256SUMS"

while read line; do
	read -a tokens <<< $line
	pkg_checksum=${tokens[0]}
	filename=${tokens[1]}
	filename=${filename/\*/}

	dest_filename="${LATEST_PATH}/${filename}"
	pkg_url="${BASE_URL}/${LATEST_VERSION}/${filename}"

	declare downloaded=false

	if [[ -f ${dest_filename} ]]; then
		echo "${pkg_checksum}  ${dest_filename}" | md5sum -c - && {
			downloaded=true
			echo "Skipping ${filename}"
		}
	fi
	while [[ $downloaded != true ]]; do
		rm ${dest_filename} || true
		echo "downloading ${pkg_url} to ${dest_filename}"
		if [[ -z ${DRY_RUN:-} ]]; then
			wget ${WGET_OPTIONS:-} -N -c -q -O ${dest_filename} ${pkg_url} && {
				# two space for md5sum/sha1sum/sha256sum check format
				echo "${pkg_checksum}  ${dest_filename}" | md5sum -c - && downloaded=true
			}
		else
			downloaded=true
		fi
	done

	case $filename in
		*Win.exe)
			ln -sf ${dest_filename} ${BASE_PATH}/virtualbox-Win-latest.exe
			;;
		*OSX.dmg)
			ln -sf ${dest_filename} ${BASE_PATH}/virtualbox-osx-latest.dmg
			;;
	esac

done < "${LATEST_PATH}/MD5SUMS"
echo "Virtualbox ${LATEST_VERSION} finished"
