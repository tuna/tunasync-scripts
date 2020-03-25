#!/bin/bash
function repo_init() {
	UPSTREAM=$1
	WORKING_DIR=$2
	git clone --mirror $UPSTREAM $WORKING_DIR
}

function update_homebrew_git() {
	repo_dir="$1"
	cd $repo_dir
	echo "==== SYNC $repo_dir START ===="
	/usr/bin/timeout -s INT 3600 git remote -v update
	objs=$(find objects/ -type f | wc -l)
	[[ "$objs" -gt 8 ]] && git repack -a -b -d
	sz=$(git count-objects -v|grep -Po '(?<=size-pack: )\d+')
	total_size=$(($total_size+1024*$sz))
	echo "==== SYNC $repo_dir DONE ===="
}

brews=("brew" "homebrew-core" "homebrew-cask" "homebrew-cask-fonts" "homebrew-cask-drivers" "linuxbrew-core")
total_size=0

for brew in ${brews[@]}; do
	if [[ ! -d "$TUNASYNC_WORKING_DIR/${brew}.git" ]]; then
		echo "Initializing ${brew}.git"
		repo_init "https://github.com/Homebrew/${brew}.git" "$TUNASYNC_WORKING_DIR/${brew}.git"
	fi
	update_homebrew_git "$TUNASYNC_WORKING_DIR/${brew}.git"
done

echo "Total size is" $(numfmt --to=iec $total_size)
