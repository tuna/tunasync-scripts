#!/bin/bash

set -xe

DESTPATH="/srv/www/homebrew"
RSYNC="/usr/bin/rsync"
LOCKFILE=/tmp/rsync-homebrew.lock

REALGIT=/home/cqumirror/.local/bin/git

RETRIES=20
DELAY=15
COUNT=1

git-retry() {
	while [ $COUNT -lt $RETRIES ]; do
		proxychains $REALGIT $*
		if [ $? -eq 0 ]; then
			RETRIES=0
			break
		fi
		let COUNT=$COUNT+1
		echo "============<"
		echo "Retry $COUNT"
		sleep $DELAY
	done
}

function repo_init() {
	UPSTREAM=$1
	WORKING_DIR=$2
	git-retry clone --ff-only --mirror $UPSTREAM $WORKING_DIR
}

function update_homebrew_git() {
	repo_dir="$1"
	cd $repo_dir
	echo "==== SYNC $repo_dir START ===="
	# /usr/bin/timeout -s INT 3600 git-retry remote -v update
	git-retry remote -v update
	git-retry repack -a -b -d
	echo "==== SYNC $repo_dir DONE ===="
}

brews=("brew" "homebrew-core" "homebrew-services" "homebrew-cask" "homebrew-cask-versions")

for brew in ${brews[@]}; do
	if [ ! -d "$DESTPATH/${brew}.git" ]; then
		echo "Initializing ${brew}.git"
		repo_init "https://github.com/Homebrew/${brew}.git" "$DESTPATH/${brew}.git"
	fi
	update_homebrew_git "$DESTPATH/${brew}.git"
done
