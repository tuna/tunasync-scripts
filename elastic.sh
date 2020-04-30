#!/bin/bash
set -e
set -o pipefail

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 
yum_sync="${_here}/yum-sync.py"

BASE_URL=${TUNASYNC_UPSTREAM_URL:-"https://artifacts.elastic.co"}

BASE_PATH="${TUNASYNC_WORKING_DIR%/}"
BASE_URL="${BASE_URL%/}"

ELASTIC_VERSION=("5.x" "6.x" "7.x")

YUM_PATH="${BASE_PATH}/yum"
APT_PATH="${BASE_PATH}/apt"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

# =================== APT repos ===============================

for elsver in "${ELASTIC_VERSION[@]}"; do
	"$apt_sync" --delete-dry-run "${BASE_URL}/packages/${elsver}/apt" stable main amd64,i386 "${APT_PATH}/${elsver}"
	
	(cd ${BASE_PATH}/${elsver}; ln -sfn ../apt/${elsver} apt)
done

# # ================ YUM/DNF repos ===============================
components="${ELASTIC_VERSION[@]}"
components=${components// /,}
"$yum_sync" "${BASE_URL}/packages/@{comp}/yum" 7 "$components" x86_64 "elastic-@{comp}" "$YUM_PATH"

for elsver in ${ELASTIC_VERSION[@]}; do
	(cd ${BASE_PATH}/${elsver}; ln -sfn ../yum/elastic-${elsver} yum)
done

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
