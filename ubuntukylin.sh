#!/bin/bash

# This script should be a cronjob and should be run a few times a day. (example for /etc/crontab: "0  *  *  *  * root /usr/bin/manjaroreposync").
# However you can also move this script to "/etc/cron.hourly".
# To be an official Manjaro Linux mirror and to get access to our rsync server, you have to tell us your static ip of your synchronization server.

DESTPATH="/srv/www/ubuntu-kylin/"
RSYNC=/usr/bin/rsync
LOCKFILE=/tmp/rsync-ubuntukylin.lock



synchronize() {
	RSYNC_PASSWORD="user"  /usr/bin/rsync -aHv -vvv --delete --progress  rsync://cdimage.ubuntukylin.com/releases/basic/ "$DESTPATH"
#	RSYNC_PASSWORD="user" $RSYNC -azHv --delete --port=8873  --progress  user@service.ubuntukylin.com::rsync "$DESTPATH"
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
        exit 0
    else
        echo $$ >"$LOCKFILE"
        echo "Warning: previous synchronization appears not to have finished correctly"
        synchronize
    fi
fi

rm -f "$LOCKFILE"
