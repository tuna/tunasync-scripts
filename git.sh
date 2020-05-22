#!/bin/bash
UPSTREAM=${TUNASYNC_UPSTREAM_URL}
if [[ -z "$UPSTREAM" ]];then
	echo "Please set the TUNASYNC_UPSTREAM_URL"
	exit 1
fi

function repo_init() {
	git clone --mirror "$UPSTREAM" "$TUNASYNC_WORKING_DIR"
}

function update_linux_git() {
	cd "$TUNASYNC_WORKING_DIR"
	echo "==== SYNC $UPSTREAM START ===="
	git remote set-url origin "$UPSTREAM"
	/usr/bin/timeout -s INT 3600 git remote -v update -p
	head=$(git remote show origin | awk '/HEAD branch:/ {print $NF}')
	[[ -n "$head" ]] && echo "ref: refs/heads/$head" > HEAD
	objs=$(find objects -type f | wc -l)
	[[ "$objs" -gt 8 ]] && git repack -a -b -d
	sz=$(git count-objects -v|grep -Po '(?<=size-pack: )\d+')
	sz=$(($sz*1024))
	echo "size-pack:" $(numfmt --to=iec $sz)
	echo "==== SYNC $UPSTREAM DONE ===="
}

if [[ ! -f "$TUNASYNC_WORKING_DIR/HEAD" ]]; then
	echo "Initializing $UPSTREAM mirror"
	repo_init
fi

update_linux_git
