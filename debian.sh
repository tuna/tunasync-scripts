#!/bin/bash
# ftpsync wrapper for tunasync
# requires: ftpsync, rsync
set -e 
set -o pipefail
set -u

export LOGNAME=tunasync
FTPSYNC="${FTPSYNC:-"ftpsync"}"
FTPSYNC_LOG_DIR="${FTPSYNC_LOG_DIR:-"/var/log/ftpsync"}"

trap 'kill $(jobs -p)' EXIT

# Clean up stale ftpsync locks left behind by killed runs.
# ftpsync normally takes over an existing lock when kill -0 on the recorded
# PID fails, but our workers run in Docker containers: a container restart
# resets the PID namespace, so the stale lock's PID can match a live
# in-container process and ftpsync keeps exiting "lock file still exists"
# forever. The 12h age limit protects a manual or push-triggered ftpsync
# currently running on the same tree. Assumes ftpsync's TO equals
# TUNASYNC_WORKING_DIR.
if [[ -n "${TUNASYNC_WORKING_DIR:-}" ]]; then
	find "${TUNASYNC_WORKING_DIR}" -maxdepth 1 -type f \
		-name 'Archive-Update-in-Progress-*' -mmin +720 -print -delete || true
fi

if [[ $1 == sync:archive:* ]]; then
	${FTPSYNC} $1 &
	PID=$!
	jobname=${1##sync:archive:}
	jobname=${jobname//\/}
	jobname=${jobname//.}
	sleep 2
	if [[ ! -f ${FTPSYNC_LOG_DIR}/ftpsync-${jobname}.log ]]; then
		echo "Failed to start ftpsync, please check configuration file."
		exit 1
	fi
	tail --retry -f "${FTPSYNC_LOG_DIR}/ftpsync-${jobname}.log" &
	tail --retry -f "${FTPSYNC_LOG_DIR}/rsync-ftpsync-${jobname}.log" &
	tail --retry -f "${FTPSYNC_LOG_DIR}/rsync-ftpsync-${jobname}.error" &
	wait $PID
	sz=$(tail -n 15 ${FTPSYNC_LOG_DIR}/rsync-ftpsync-${jobname}.log.0|grep -Po '(?<=Total file size: )\d+')
	[[ -z "$sz" ]] || echo "Total size is" $(numfmt --to=iec $sz)
else
	echo "Invalid command line"
	exit 1
fi
