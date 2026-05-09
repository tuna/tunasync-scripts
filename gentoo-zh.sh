#!/bin/bash

# This script should be a cronjob and should be run a few times a day. (example for /etc/crontab: "0  *  *  *  * root /usr/bin/manjaroreposync").
# However you can also move this script to "/etc/cron.hourly".
# To be an official Manjaro Linux mirror and to get access to our rsync server, you have to tell us your static ip of your synchronization server.

DESTPATH="/srv/www/gentoo-zh.git/"
RSYNC=/usr/bin/rsync
LOCKFILE=/tmp/rsync-gentoo-zh.lock

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
#    $RSYNC -rtlvH --delete-after --delay-updates --safe-links \
# rsync://rsync.jp.gentoo.org/gentoo-portage/  "$DESTPATH"
	cd $DESTPATH
	echo "Pulling from source..."
	git-retry pull --ff-only
	echo "repacking ..."
	echo ""
	git-retry repack -a -d -b
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
