#!/bin/bash

# This script should be a cronjob and should be run a few times a day. (example for /etc/crontab: "0  *  *  *  * root /usr/bin/manjaroreposync").
# However you can also move this script to "/etc/cron.hourly".
# To be an official Manjaro Linux mirror and to get access to our rsync server, you have to tell us your static ip of your synchronization server.

DESTPATH="/srv/www/ceph/"
RSYNC=/usr/bin/rsync
LOCKFILE=/tmp/rsync-archlinuxcn.lock
UPSTREAM_URL="rsync://download.ceph.com/ceph"


synchronize() {
	/usr/bin/rsync -rtlivH --delete-after --delay-updates --safe-links --max-delete=1000 --contimeout=60 -vvv "$UPSTREAM_URL"  "$DESTPATH"
}



if [ ! -e "$LOCKFILE" ]
then
    echo $$ >"$LOCKFILE"
    synchronize
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
	exit 0
    fi
fi

rm -f "$LOCKFILE"
