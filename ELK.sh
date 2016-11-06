#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
. ${_here}/helpers/apt-download

[ -z "${LOADED_APT_DOWNLOAD}" ] && (echo "failed to load apt-download"; exit 1)

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packages.elastic.co"}

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"

declare -A REPO_VERSIONS=(
	["elasticsearch"]="2.x"
	["logstash"]="2.3 2.4 5.0"
	["kibana"]="4.5 4.6"
)

mkdir -p ${YUM_PATH} ${APT_PATH}

# =================== APT repos ===============================
if [[ ! -z ${DRY_RUN:-} ]]; then
	export APT_DRY_RUN=1
fi
 
for repo in "${!REPO_VERSIONS[@]}"; do
	# magic here, don't quote ${REPO_VERSIONS[$repo][@]}
	# so that bash loops over space-sperated tokens
	for version in ${REPO_VERSIONS[$repo]}; do
		echo $repo-$version
		apt_url="${BASE_URL}/${repo}/${version}/debian"
		dest_path="${APT_PATH}/${repo}/${version}"
		[[ ! -d ${dest_path} ]] && mkdir -p ${dest_path}
		apt-download-binary ${apt_url} "stable" "main" "amd64" "${dest_path}" || true
		apt-download-binary ${apt_url} "stable" "main" "i386" "${dest_path}" || true
	done
done

# ================ YUM/DNF repos ===============================

cache_dir="/tmp/yum-elk-cache/"
cfg="/tmp/yum-elk.conf"
cat <<EOF > ${cfg}
[main]
keepcache=0

EOF

for repo in "${!REPO_VERSIONS[@]}"; do
for version in ${REPO_VERSIONS[$repo]}; do
cat <<EOF >> ${cfg}
[${repo}-${version}]
name=${repo} ${version} packages
baseurl=${BASE_URL}/${repo}/${version}/centos
repo_gpgcheck=0
gpgcheck=0
enabled=1
sslverify=0

EOF
done
done

if [[ -z ${DRY_RUN:-} ]]; then
	reposync -c $cfg -d -p ${YUM_PATH} -e ${cache_dir}
	for repo in "${!REPO_VERSIONS[@]}"; do
		for version in ${REPO_VERSIONS[$repo]}; do
			createrepo --update -v -c ${cache_dir} -o ${YUM_PATH}/${repo}-${version}/ ${YUM_PATH}/${repo}-${version}/
		done
	done
fi
rm $cfg
