#!/bin/bash

set -xe
# This script should be a cronjob and should be run a few times a day. (example for /etc/crontab: "0  *  *  *  * root /usr/bin/manjaroreposync").
# However you can also move this script to "/etc/cron.hourly".
# To be an official Manjaro Linux mirror and to get access to our rsync server, you have to tell us your static ip of your synchronization server.

DESTPATH="/srv/www/alpine/"
# PROXY=/usr/bin/proxychains
RSYNC=/usr/bin/rsync
# RSYNC=/home/cqumirror/.local/bin/rsync
LOCKFILE=/tmp/rsync-alpine.lock
# UPSTREAM_URL="rsync://rsync.alpinelinux.org/alpine/"
UPSTREAM_URL="rsync://mirrors.tuna.tsinghua.edu.cn/alpine"
TRUE=/bin/true
#VVV="-VVV"
VVV=""

synchronize() {
	# run synchronize
        $PROXY $RSYNC -rtlivHi $VVV  \
	       --stats \
	       --filter 'risk .~tmp~/' \
	       --temp-dir=$TMP_DIR  \
	       --delete-after \
	       --safe-links \
	       --delay-updates  \
	       --contimeout=6000000 \
	       --exclude='.~tmp~/'  \
	       --exclude='/edge/' \
	       --exclude='/v3.19/' \
	       --exclude='/v3.18/' \
	       --exclude='/v3.17/' \
	       --exclude='/v3.16/' \
	       --exclude='/v3.15/' \
	       --exclude='/v3.14/' \
	       --exclude='/v3.13/' \
	       --exclude='/v3.12/' \
               --exclude='/v3.11/' \
               --exclude='/v3.10/' \
	       --exclude='/v3.9/' \
	       --exclude='/v3.8/' \
	       --exclude='/v3.7/' \
	       --exclude='/v3.6/' \
               --exclude='/v3.5/' \
	       --exclude='/v3.4/' \
	       --exclude='/v3.3/' \
	       --exclude='/v3.2/' \
	       --exclude='/v3.1/' \
	       --exclude='/v3.0/' \
	       --delete-excluded  "$UPSTREAM_URL"  "$DESTPATH" || $TRUE
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

