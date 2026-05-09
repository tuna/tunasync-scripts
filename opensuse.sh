#!/bin/bash

set -xe
# This script should be a cronjob and should be run a few times a day. (example for /etc/crontab: "0  *  *  *  * root /usr/bin/manjaroreposync").
# However you can also move this script to "/etc/cron.hourly".
# To be an official Manjaro Linux mirror and to get access to our rsync server, you have to tell us your static ip of your synchronization server.

DESTPATH="/srv/www/opensuse/"
TMP_DIR="/srv/www/opensuse/rsync_tmp/opensuse"
# PROXY=/usr/bin/proxychains
# RSYNC=/usr/bin/rsync
RSYNC=/home/cqumirror/.local/bin/rsync
LOCKFILE=/tmp/rsync-opensuse.lock
#UPSTREAM_URL="rsync://ftp.gwdg.de/pub/opensuse/"
UPSTREAM_URL="rsync://mirrors.ustc.edu.cn/opensuse/"
#UPSTREAM_URL="rsync://mirrors.ocf.berkeley.edu/opensuse/"
#UPSTREAM_URL="rsync://mirrors.tuna.tsinghua.edu.cn/opensuse/"
TRUE=/bin/true
#VVV="-VVV"
VVV=""
V4V6=-4

synchronize() {
	# create tmp dir
	mkdir -p $TMP_DIR
	# run synchronize
       $PROXY $RSYNC -rtlivHi $VVV $V4V6  \
	       --stats \
               --timeout=360 \
               --partial-dir=.rsync-partial \
	       --filter 'risk .~tmp~/' \
	       --temp-dir=$TMP_DIR  \
	       --delete-after \
	       --safe-links \
	       --delay-updates  \
	       --contimeout=6000000 \
	       --exclude='/FOSDEM/' \
	       --exclude='/debug/' \
	       --exclude='/education/' \
	       --exclude='/project/' \
	       --exclude='*-debuginfo-*' \
	       --exclude='*-debugsource-*' \
	       --exclude='/history/' \
	       --exclude='/source/' \
	       --exclude='/tumbleweed/repo/src-non-oss/' \
	       --exclude='/tumbleweed/repo/src-oss/' \
	       --exclude='/distribution/leap/42.3/iso/' \
	       --exclude='/distribution/leap/42.3/jeos/' \
	       --exclude='/distribution/leap/42.3/live/' \
	       --exclude='/distribution/leap/15.0/iso/' \
	       --exclude='/distribution/leap/15.0/jeos/' \
	       --exclude='/distribution/leap/15.0/live/' \
	       --exclude='/distribution/leap/15.1/iso/' \
	       --exclude='/distribution/leap/15.1/jeos/' \
	       --exclude='/distribution/leap/15.1/live/' \
	       --exclude='/distribution/leap/15.2/iso/' \
	       --exclude='/distribution/leap/15.2/jeos/' \
	       --exclude='/distribution/leap/15.2/live/' \
	       --exclude='/distribution/leap/15.3/iso/' \
	       --exclude='/distribution/leap/15.3/jeos/' \
	       --exclude='/distribution/leap/15.3/live/' \
	       --exclude='/update/*/*/*_debug/' \
	       --exclude='/update/*/*/*/src/' \
	       --exclude='/ports/*/source' \
	       --exclude='/ports/*/*/appliances/*' \
	       --exclude='/ports/armv6hl/' \
	       --exclude='/ports/armv7hl/' \
	       --exclude='/ports/debug/' \
	       --exclude='/ports/ppc/' \
	       --exclude='/ports/zsystems/' \
	       --exclude='/ports/riscv/' \
	       --exclude='/ports/update/*/*/*/armv7hl/' \
	       --exclude='/ports/update/*/*/*/armv6hl/' \
	       --exclude='/ports/update/*/*/*/ppc/' \
	       --exclude='/ports/update/*/*/*/zsystems/' \
	       --exclude='/ports/update/*/*/*/debug/' \
	       --exclude='/ports/update/*/*/*/riscv/' \
	       --exclude='/ports/*/*/*/*/src/' \
	       --exclude='/ports/*/*/*/*_debug/' \
	       --exclude='/distribution/*/*/product/repo/*/src/' \
	       --exclude='/distribution/*/*/appliances/*' \
	       --exclude='/tumbleweed/appliances/*' \
	       --exclude='ppc64le/' \
	       --exclude='s390x/' \
	       --exclude='*ppc64le*.iso' \
	       --exclude="*s390x*iso" \
	       --exclude='.~tmp~/'  \
	       --exclude='/discontinued' \
	       --exclude='/repositories' \
	       --exclude='/slowroll/next-full' \
	       --exclude='/slowroll/next' \
	       "$UPSTREAM_URL"  "$DESTPATH"
       ret=$?
	rm -rf $TMP_DIR
	return $ret
}


if [ ! -e "$LOCKFILE" ]
then
    echo $$ >"$LOCKFILE"
    synchronize
    ret=$?
    rm -rf $LOCKFILE
    exit $ret
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
	ret=$?
	rm -rf $LOCKFILE
	exit $ret
    fi
fi

