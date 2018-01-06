#!/bin/bash

thread=${TUNASYNC_LFTP_CONCURRENT:-"5"}
opts=${TUNASYNC_LFTP_OPTIONS:-""}


[ ! -d "${TUNASYNC_WORKING_DIR}" ] && mkdir -p "${TUNASYNC_WORKING_DIR}"
cd ${TUNASYNC_WORKING_DIR}
lftp "${TUNASYNC_UPSTREAM_URL}" -e "mirror --verbose --skip-noaccess -P ${thread} --delete ${opts} ; bye"
