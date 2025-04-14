#!/bin/bash

if [[ ! -z "${TUNASYNC_S3_ENDPOINT}" ]]; then
	ENDPOINT="--endpoint-url=${TUNASYNC_S3_ENDPOINT}"
else
	ENDPOINT=""
fi

# see tuna/tunasync-scripts#183
export AWS_EC2_METADATA_DISABLED=true

[[ ! -d "${TUNASYNC_WORKING_DIR}" ]] && mkdir -p "${TUNASYNC_WORKING_DIR}"
mkdir /tmp/none; cd /tmp/none # enter an empty folder, so the stars in TUNASYNC_AWS_OPTIONS are not expanded
exec aws --no-sign-request ${ENDPOINT} s3 sync --exact-timestamps ${TUNASYNC_AWS_OPTIONS} "${TUNASYNC_UPSTREAM_URL}" "${TUNASYNC_WORKING_DIR}"

