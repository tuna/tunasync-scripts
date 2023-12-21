#!/usr/bin/env bash

#. /path/to/sync-utils.sh || {
#    echo Failed to load sync-utils.sh >&2
#    exit 1
#}
. "$(dirname -- "$0")"/sync-utils.sh || {
	    echo Failed to load sync-utils.sh >&2
    exit 1
}

URL=cran.r-project.org::CRAN
URL=rsync://mirrors.tuna.tsinghua.edu.cn/CRAN/
DST=/srv/www/cran
# TEMP_DIR=/path/to/temp/dir

# The following one job is interruptible. For example, killed by tunasync when
# `tunasync stop job-name` is run by user manually.
run-sync-job rsync -rptlzvH \
		   --delete-after \
		   --delay-updates \
		   --safe-links "$URL" "$DST"

# using the exit status to tell caller whether the job success is IMPORTANT!
ret=$?

# If rsync failed, it might leave some temporary files.
if [ $ret != 0 ]; then
	    # with signals blocked, it should not run for too long.
	        rm -rf "$TEMP_DIR"
		    # If we are unsure that whether time needed by the cleanup is short enough,
		        # we can use the following one instead:
			    #timeout 1 rm -rf "$TEMP_DIR"
fi

# return the status of sync
exit $ret
