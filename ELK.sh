#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_PATH="${TUNASYNC_WORKING_DIR}"
BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://packages.elastic.co"}

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"

export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

declare -A REPO_VERSIONS=(
	["elasticsearch"]="2.x"
	["logstash"]="2.3 2.4 5.0"
	["kibana"]="4.5 4.6"
)

# =================== APT repos ===============================
 
for repo in "${!REPO_VERSIONS[@]}"; do
	# magic here, don't quote ${REPO_VERSIONS[$repo][@]}
	# so that bash loops over space-sperated tokens
	for version in ${REPO_VERSIONS[$repo]}; do
		echo $repo-$version
		apt_url="${BASE_URL}/${repo}/${version}/debian"
		dest_path="${APT_PATH}/${repo}/${version}"
		"$apt_sync" --delete-dry-run "$apt_url" stable main amd64,i386 "$dest_path"
	done
done

# ================ YUM/DNF repos ===============================

for repo in "${!REPO_VERSIONS[@]}"; do
	versions=${REPO_VERSIONS[$repo]}
	components=${versions// /,}
	"$yum_sync" "${BASE_URL}/${repo}/@{comp}/centos/" 7 "$components" x86_64 "${repo}-@{comp}" "$YUM_PATH"
done

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm