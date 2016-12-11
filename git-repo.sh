#!/bin/bash
UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://gerrit.googlesource.com/git-repo"}

function repo_init() {
	git clone --mirror $UPSTREAM $TUNASYNC_WORKING_DIR
}

function update_repo_git() {
	cd $TUNASYNC_WORKING_DIR
	echo "==== SYNC repo.git START ===="
	/usr/bin/timeout -s INT 3600 git remote -v update
	git repack -a -b -d
	echo "==== SYNC repo.git DONE ===="
}

function checkout_repo() {
    git -C $TUNASYNC_WORKING_DIR show HEAD:repo > $TUNASYNC_WORKING_DIR/git-repo
}

if [[ ! -f "$TUNASYNC_WORKING_DIR/HEAD" ]]; then
	echo "Initializing repo.git mirror"
	repo_init
fi

update_repo_git
checkout_repo
