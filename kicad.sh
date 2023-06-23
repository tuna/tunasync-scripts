#!/bin/bash

# This script should be a cronjob and should be run a few times a day. (example for /etc/crontab: "0  *  *  *  * root /usr/bin/manjaroreposync").
# However you can also move this script to "/etc/cron.hourly".
# To be an official Manjaro Linux mirror and to get access to our rsync server, you have to tell us your static ip of your synchronization server.

DESTPATH="/srv/www/kicad/"
LOCKFILE=/tmp/rsync-kicad.lock


synchronize() {
	# sync
	aws --no-sign-request \
	    --endpoint-url='https://s3.cern.ch/' s3 sync s3://kicad-downloads/ $DESTPATH \
	    --exclude "windows/nightly/*" \
	    --exclude "windows/testing/*" \
	    --exclude "osx/nightly/*" \
	    --exclude "osx/testing/*" \
	    --exclude index.html
	#    --dryrun
	# clean up
	cd $DESTPATH/windows/stable && rm .[^.]*
	cd $DESTPATH/osx/stable && rm .[^.]*
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

exec rm -f "$LOCKFILE"
