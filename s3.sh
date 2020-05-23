#!/bin/bash

[[ ! -d "${TUNASYNC_WORKING_DIR}" ]] && mkdir -p "${TUNASYNC_WORKING_DIR}"
mkdir /tmp/none; cd /tmp/none # enter an empty folder, so the stars in TUNASYNC_AWS_OPTIONS are not expanded
exec aws --no-sign-request --endpoint-url="${TUNASYNC_S3_ENDPOINT}" s3 sync ${TUNASYNC_AWS_OPTIONS} "${TUNASYNC_UPSTREAM_URL}" "${TUNASYNC_WORKING_DIR}"
