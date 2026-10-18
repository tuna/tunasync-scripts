#!/bin/bash

thread=${TUNASYNC_LFTP_CONCURRENT:-"5"}
opts=${TUNASYNC_LFTP_OPTIONS:-""}
ua=${TUNASYNC_LFTP_USER_AGENT:-"tunasync-scripts (+https://github.com/tuna/tunasync-scripts)"}


[ ! -d "${TUNASYNC_WORKING_DIR}" ] && mkdir -p "${TUNASYNC_WORKING_DIR}"
cd ${TUNASYNC_WORKING_DIR}
lftp "${TUNASYNC_UPSTREAM_URL}" -e "set http:user-agent ${ua}; mirror --verbose --skip-noaccess -P ${thread} --delete ${opts} ; bye"
