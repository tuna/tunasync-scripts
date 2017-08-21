#!/bin/bash

BASE_URL=${TUNASYNC_UPSTREAM_URL:-"http://archive.raspberrypi.org/debian/"}

cd "$TUNASYNC_WORKING_DIR"
lftp "$BASE_URL" -e "mirror --verbose -P 5 --delete --only-newer; bye"
