#!/bin/bash
set -e

REPO=${REPO:-"/usr/local/bin/repo"}
USE_BITMAP_INDEX=${USE_BITMAP_INDEX:-"0"}
UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://android.googlesource.com/mirror/manifest"}

function repo_init() {
	mkdir -p $TUNASYNC_WORKING_DIR
	cd $TUNASYNC_WORKING_DIR
	$REPO init -u $UPSTREAM --mirror
}

function repo_sync() {
	cd $TUNASYNC_WORKING_DIR
	$REPO sync -f
}

function git_repack() {
	echo "Start writing bitmap index"
	while read repo; do 
		cd $repo
		size=$(du -sm .|cut -f1)
		if [[ "$size" -gt "100" ]]; then
			echo $repo, ${size}M
			git repack -a -b -d
		fi
	done < <(find $TUNASYNC_WORKING_DIR -type d -not -path "*/.repo/*" -name "*.git")
}

if [[ ! -d "$TUNASYNC_WORKING_DIR/git-repo.git" ]]; then
	echo "Initializing AOSP mirror"
	repo_init
fi

repo_sync

if [[ "$USE_BITMAP_INDEX" == "1" ]]; then
	git_repack
fi
