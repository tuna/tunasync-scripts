#!/bin/bash
set -e 
set -o pipefail
set -u

export LOGNAME=tunasync
FTPSYNC="${FTPSYNC:-"ftpsync"}"
FTPSYNC_LOG_DIR="${FTPSYNC_LOG_DIR:-"/var/log/ftpsync"}"

trap 'kill $(jobs -p)' EXIT

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
