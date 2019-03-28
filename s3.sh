#!/bin/bash

[ ! -d "${TUNASYNC_WORKING_DIR}" ] && mkdir -p "${TUNASYNC_WORKING_DIR}"
aws --no-sign-request --endpoint-url="${TUNASYNC_S3_ENDPOINT}" s3 sync ${TUNASYNC_AWS_OPTIONS} "${TUNASYNC_UPSTREAM_URL}" "${TUNASYNC_WORKING_DIR}"
