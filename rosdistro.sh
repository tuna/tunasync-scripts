#!/bin/bash
set -e

git_option="git -c user.email=non-existence@tuna.tsinghua.edu.cn -c user.name=Noname"

function repo_init() {
        UPSTREAM="$1"
        WORKING_DIR="$2"
        git clone "$UPSTREAM" "$WORKING_DIR"
}

function update_git() {
	UPSTREAM="$1"
        repo_dir="$2"
        cd "$repo_dir"
        echo "==== SYNC $repo_dir START ===="
	git remote set-url origin "$UPSTREAM"
        /usr/bin/timeout -s INT 3600 git remote -v update -p
	head=$(git remote show origin | awk '/HEAD branch:/ {print $NF}')
	[[ -n "$head" ]] && echo "ref: refs/heads/$head" > HEAD
        objs=$(find objects -type f | wc -l)
        [[ "$objs" -gt 8 ]] && git repack -a -b -d
        sz=$(git count-objects -v|grep -Po '(?<=size-pack: )\d+')
        total_size=$(($total_size+1024*$sz))
        echo "==== SYNC $repo_dir DONE ===="
}

function checkout_branch() {
	repo_dir="$1"
	work_tree="$2"
	branch="$3"
	echo "Checkout branch $branch to $work_tree"
	if [[ ! -d "$2" ]]; then
		$git_option clone "$repo_dir" --branch "$branch" --single-branch "$work_tree"
	else
		cd "$work_tree"
		$git_option pull
	fi
}

UPSTREAM_BASE=${TUNASYNC_UPSTREAM_URL:-"https://github.com/ros/rosdistro"}
total_size=0

if [[ ! -d "$TUNASYNC_WORKING_DIR/.git" ]]; then
        echo "Initializing"
        repo_init "${UPSTREAM_BASE}" "$TUNASYNC_WORKING_DIR"
fi
update_git "${UPSTREAM_BASE}" "$TUNASYNC_WORKING_DIR/.git"
checkout_branch "$TUNASYNC_WORKING_DIR/.git" "$TUNASYNC_WORKING_DIR" "master"

echo "Total size is" $(numfmt --to=iec $total_size)
