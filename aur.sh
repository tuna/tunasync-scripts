#!/bin/bash
UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://github.com/archlinux/aur.git"}
WORKDIR=/tank/mirror-data/git/aur.git
function repo_init() {
	git clone $UPSTREAM $WORKDIR
	# $TUNASYNC_WORKING_DIR
}

function update_repo_git() {
	cd $WORKDIR 
	# $TUNASYNC_WORKING_DIR
	echo "==== SYNC ArchLinux AUR GITHUB Mirror START ===="
	/usr/bin/timeout -s INT 3600 git fetch --all || {
		echo "=== SYNC Archlinux AUR GITHUB Mirror FAILED ==="
		exit 1
	}
	git reset --hard origin/master
	git repack -a -b -d
	echo "==== SYNC ArchLinux AUR GITHUB Mirror DONE ===="
}

# if [[ ! -f "$TUNASYNC_WORKING_DIR/.git/HEAD" ]]; then
if [[ ! -f "$WORKDIR/.git/HEAD" ]]; then
	echo "Initializing AUR Github mirror"
	repo_init
fi

update_repo_git
