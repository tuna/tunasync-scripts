#!/bin/bash

set -xe
# This script should be a cronjob and should be run a few times a day. (example for /etc/crontab: "0  *  *  *  * root /usr/bin/manjaroreposync").
# However you can also move this script to "/etc/cron.hourly".
# To be an official Manjaro Linux mirror and to get access to our rsync server, you have to tell us your static ip of your synchronization server.

DESTPATH="/srv/www/opensuse/"
TMP_DIR="/tank/mirror-data/rsync_tmp/opensuse"
PROXY=/usr/bin/proxychains
# RSYNC=/usr/bin/rsync
RSYNC=/home/cqumirror/.local/bin/rsync
LOCKFILE=/tmp/rsync-opensuse.lock
UPSTREAM_URL="rsync://ftp.riken.jp/opensuse/"
# UPSTREAM_URL="rsync://mirrors.tuna.tsinghua.edu.cn/opensuse/"
TRUE=/bin/true
VVV=""

synchronize() {
	# create tmp dir
	mkdir -p $TMP_DIR
	# run synchronize
       $PROXY $RSYNC -rtlivHi $VVV  \
	       --stats \
	       --filter 'risk .~tmp~/' \
	       --temp-dir=$TMP_DIR  \
	       --delete-after \
	       --safe-links \
	       --delay-updates  \
	       --contimeout=6000000 \
	       --exclude='/history/' \
	       --exclude='/update/*/*/*_debug/' \
	       --exclude='.~tmp~/'  \
	       --delete-excluded  "$UPSTREAM_URL"  "$DESTPATH" || $TRUE
# $PROXY $RSYNC -rtlivH --delete-after --delay-updates --safe-links  --contimeout=6000000 --exclude='/history/' --exclude='/update/*/*/*_debug/' --delete-excluded  "$UPSTREAM_URL"  "$DESTPATH"
	rm -rf $TMP_DIR
}


if [ ! -e "$LOCKFILE" ]
then
    echo $$ >"$LOCKFILE"
    synchronize
    rm -rf $LOCKFILE
else
    PID=$(cat "$LOCKFILE")
    if kill -0 "$PID" >&/dev/null
    then
        echo "Rsync - Synchronization still running"
        exit 15
    else
        echo $$ >"$LOCKFILE"
        echo "Warning: previous synchronization appears not to have finished correctly"
        synchronize
	rm -rf $LOCKFILE
    fi
fi

