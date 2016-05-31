#!/bin/bash
set -e

function repo_init() {
	UPSTREAM=$1
	WORKING_DIR=$2
	git clone --mirror $UPSTREAM $WORKING_DIR
}

function update_cocoapods_git() {
	repo_dir="$1"
	cd $repo_dir
	echo "==== SYNC $repo_dir START ===="
	/usr/bin/timeout -s INT 3600 git remote -v update
	git repack -a -b -d
	echo "==== SYNC $repo_dir DONE ===="
}

UPSTREAM_BASE=${TUNASYNC_UPSTREAM_URL:-"https://github.com/CocoaPods"}
REPOS=("Specs")

for repo in ${REPOS[@]}; do
	if [[ ! -d "$TUNASYNC_WORKING_DIR/${repo}.git" ]]; then
		echo "Initializing ${repo}.git"
		repo_init "${UPSTREAM_BASE}/${repo}.git" "$TUNASYNC_WORKING_DIR/${repo}.git"
	fi
	update_cocoapods_git "$TUNASYNC_WORKING_DIR/${repo}.git"
done
