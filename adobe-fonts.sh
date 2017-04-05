#!/bin/bash
set -e

function repo_init() {
        UPSTREAM="$1"
        WORKING_DIR="$2"
        git clone --mirror "$UPSTREAM" "$WORKING_DIR" 
}

function update_font_git() {
        repo_dir="$1"
        cd "$repo_dir"
        echo "==== SYNC $repo_dir START ===="
        /usr/bin/timeout -s INT 3600 git remote -v update
        git repack -a -b -d
        echo "==== SYNC $repo_dir DONE ===="
}

function checkout_font_branch() {
	repo_dir="$1"
	work_tree="$2"
	branch="$3"
	echo "Checkout branch $branch to $work_tree"
	if [[ ! -d "$2" ]]; then
		git clone "$repo_dir" --branch "$branch" --single-branch "$work_tree"
	else
		cd "$work_tree"
		git pull
	fi
}

UPSTREAM_BASE=${TUNASYNC_UPSTREAM_URL:-"https://github.com/adobe-fonts"}
REPOS=("source-code-pro" "source-sans-pro" "source-serif-pro" "source-han-sans" "source-han-serif")

for repo in ${REPOS[@]}; do
        if [[ ! -d "$TUNASYNC_WORKING_DIR/${repo}.git" ]]; then
                echo "Initializing ${repo}.git"
                repo_init "${UPSTREAM_BASE}/${repo}.git" "$TUNASYNC_WORKING_DIR/${repo}.git"
        fi
        update_font_git "$TUNASYNC_WORKING_DIR/${repo}.git"
	checkout_font_branch "$TUNASYNC_WORKING_DIR/${repo}.git" "$TUNASYNC_WORKING_DIR/${repo}" "release"
done
