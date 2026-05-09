#!/bin/bash

# This script should be a cronjob and should be run a few times a day. (example for /etc/crontab: "0  *  *  *  * root /usr/bin/manjaroreposync").
# However you can also move this script to "/etc/cron.hourly".
# To be an official Manjaro Linux mirror and to get access to our rsync server, you have to tell us your static ip of your synchronization server.

DESTPATH="/srv/www/gentoo-zh/"
RSYNC=/usr/bin/rsync
LOCKFILE=/tmp/rsync-gentoo-zh-binhost.lock
UPSTREAM_URL=rsync://distfiles.gentoocn.org/gentoo-zh/ # See <https://fedoraproject.org/wiki/Infrastructure/Mirroring/Tiering#Tier_1_Mirrors>


synchronize() {
	/usr/bin/rsync -rtlivH --delete-after --delay-updates --safe-links --contimeout=900 "$UPSTREAM_URL"  "$DESTPATH"
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
    fi
fi

rm -f "$LOCKFILE"
