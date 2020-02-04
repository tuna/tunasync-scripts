#!/bin/bash
UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"}

function repo_init() {
	git clone --mirror $UPSTREAM $TUNASYNC_WORKING_DIR
}

function update_linux_git() {
	cd $TUNASYNC_WORKING_DIR
	echo "==== SYNC $UPSTREAM START ===="
	/usr/bin/timeout -s INT 3600 git remote -v update
	git repack -a -b -d
	echo "==== SYNC $UPSTREAM DONE ===="
}

if [[ ! -f "$TUNASYNC_WORKING_DIR/HEAD" ]]; then
	echo "Initializing $UPSTREAM mirror"
	repo_init
fi

update_linux_git
