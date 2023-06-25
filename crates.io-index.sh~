#!/bin/bash

# This script should be a cronjob and should be run a few times a day. (example for /etc/crontab: "0  *  *  *  * root /usr/bin/manjaroreposync").
# However you can also move this script to "/etc/cron.hourly".
# To be an official Manjaro Linux mirror and to get access to our rsync server, you have to tell us your static ip of your synchronization server.

DESTPATH="/srv/www/git/crates.io-index/"
RSYNC=/usr/bin/rsync
LOCKFILE=/tmp/rsync-aur.lock

REALGIT=/home/cqumirror/.local/bin/git

RETRIES=5
DELAY=10
COUNT=1

git-retry() {
	while [ $COUNT -lt $RETRIES ]; do
		$REALGIT $*
		if [ $? -eq 0 ]; then
			RETRIES=0
			break
		fi
		let COUNT=$COUNT+1
		echo "============"
		echo "Retry $COUNT"
		echo ""
		sleep $DELAY
	done
}

synchronize() {
	cd $DESTPATH
	# git-retry clone $UPSTREAM $DESTPATH
	echo "Pulling from source..."
	git-retry pull --ff-only
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

exec rm -f "$LOCKFILE"
