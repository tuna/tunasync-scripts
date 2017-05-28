#!/bin/bash
function repo_init() {
	UPSTREAM=$1
	WORKING_DIR=$2
	git clone --mirror $UPSTREAM $WORKING_DIR
}

function repo_update() {
	repo_dir="$1"
	cd $repo_dir
	echo "==== SYNC $repo_dir START ===="
	/usr/bin/timeout -s INT 3600 git remote -v update
	git repack -a -b -d
	echo "==== SYNC $repo_dir DONE ===="
}

repos=("llvm" "clang" "libcxx" "lldb" "clang-tools-extra" "polly" "zorg" "compiler-rt" "libcxxabi" "lld" "lnt")

for repo in ${repos[@]}; do
	if [[ ! -d "$TUNASYNC_WORKING_DIR/${repo}.git" ]]; then
		echo "Initializing ${repo}.git"
		repo_init "http://llvm.org/git/${repo}" "$TUNASYNC_WORKING_DIR/${repo}.git"
	fi
	repo_update "$TUNASYNC_WORKING_DIR/${repo}.git"
done
