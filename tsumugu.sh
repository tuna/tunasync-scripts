#!/bin/bash

set -eu

TUNASYNC_TSUMUGU_MAXDELETE=${TUNASYNC_TSUMUGU_MAXDELETE:-1000}
TUNASYNC_TSUMUGU_TIMEZONEFILE=${TUNASYNC_TSUMUGU_TIMEZONEFILE:-}
TUNASYNC_TSUMUGU_EXCLUDE=${TUNASYNC_TSUMUGU_EXCLUDE:-}
TUNASYNC_TSUMUGU_USERAGENT=${TUNASYNC_TSUMUGU_USERAGENT:-"tsumugu/"$(tsumugu --version | tail -n1 | cut -d' ' -f2)}
TUNASYNC_TSUMUGU_PARSER=${TUNASYNC_TSUMUGU_PARSER:-"nginx"}
TUNASYNC_TSUMUGU_THREADS=${TUNASYNC_TSUMUGU_THREADS:-"2"}
TUNASYNC_TSUMUGU_OPTIONS=${TUNASYNC_TSUMUGU_OPTIONS:-}

if [[ -n $TUNASYNC_TSUMUGU_TIMEZONEFILE ]]; then
    TUNASYNC_TSUMUGU_TIMEZONEFILE="--timezone-file $TUNASYNC_TSUMUGU_TIMEZONEFILE"
fi

export NO_COLOR=1

[ ! -d "${TUNASYNC_WORKING_DIR}" ] && mkdir -p "${TUNASYNC_WORKING_DIR}"
cd ${TUNASYNC_WORKING_DIR}

exec tsumugu sync $TUNASYNC_TSUMUGU_TIMEZONEFILE --user-agent "$TUNASYNC_TSUMUGU_USERAGENT" --max-delete "$TUNASYNC_TSUMUGU_MAXDELETE" --parser "$TUNASYNC_TSUMUGU_PARSER" --threads "$TUNASYNC_TSUMUGU_THREADS" $TUNASYNC_TSUMUGU_EXCLUDE $TUNASYNC_TSUMUGU_OPTIONS "$TUNASYNC_UPSTREAM_URL" "$TUNASYNC_WORKING_DIR"
