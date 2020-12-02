#!/bin/bash
function repo_init() {
	UPSTREAM=$1
	WORKING_DIR=$2
	git clone --mirror $UPSTREAM $WORKING_DIR
}

function update_homebrew_git() {
	UPSTREAM="$1"
	repo_dir="$2"
	cd $repo_dir
	echo "==== SYNC $repo_dir START ===="
	git remote set-url origin "$UPSTREAM"
	/usr/bin/timeout -s INT 3600 git remote -v update -p
	head=$(git remote show origin | awk '/HEAD branch:/ {print $NF}')
	[[ -n "$head" ]] && echo "ref: refs/heads/$head" > HEAD
	objs=$(find objects/ -type f | wc -l)
	[[ "$objs" -gt 8 ]] && git repack -a -b -d
	sz=$(git count-objects -v|grep -Po '(?<=size-pack: )\d+')
	total_size=$(($total_size+1024*$sz))
	echo "==== SYNC $repo_dir DONE ===="
}

UPSTREAM_BASE=${TUNASYNC_UPSTREAM_URL:-"https://github.com/Homebrew"}
brews=("brew" "homebrew-core" "homebrew-cask" "homebrew-cask-fonts" "homebrew-cask-drivers" "linuxbrew-core" "install")
total_size=0

for brew in ${brews[@]}; do
	if [[ ! -d "$TUNASYNC_WORKING_DIR/${brew}.git" ]]; then
		echo "Initializing ${brew}.git"
		repo_init "${UPSTREAM_BASE}/${brew}.git" "$TUNASYNC_WORKING_DIR/${brew}.git"
	fi
	update_homebrew_git "${UPSTREAM_BASE}/${brew}.git" "$TUNASYNC_WORKING_DIR/${brew}.git"
done

echo "Total size is" $(numfmt --to=iec $total_size)
