#!/bin/bash
# Sync Scoop and its official "known buckets" as subdirectories of one mirror.
# Bucket list: https://github.com/ScoopInstaller/Scoop/blob/master/buckets.json
# Note that some known buckets are hosted outside the ScoopInstaller org;
# local directory names follow the upstream repository names.

function repo_init() {
	UPSTREAM=$1
	WORKING_DIR=$2
	git clone --mirror "$UPSTREAM" "$WORKING_DIR"
}

function update_git() {
	UPSTREAM="$1"
	repo_dir="$2"
	cd "$repo_dir" || { echo "ERROR: cannot cd to $repo_dir" >&2; return 1; }
	echo "==== SYNC $repo_dir START ===="
	git remote set-url origin "$UPSTREAM" || return 1
	/usr/bin/timeout -s INT 3600 git remote -v update -p || return 1
	head=$(git remote show origin | awk '/HEAD branch:/ {print $NF}')
	[[ -n "$head" ]] && echo "ref: refs/heads/$head" > HEAD
	objs=$(find objects/ -type f | wc -l)
	if [[ "$objs" -gt 8 ]]; then
		git repack -a -b -d || return 1
	fi
	sz=$(git count-objects -v|grep -Po '(?<=size-pack: )\d+')
	total_size=$(($total_size+1024*$sz))
	echo "==== SYNC $repo_dir DONE ===="
}

UPSTREAM_BASE=${TUNASYNC_UPSTREAM_URL:-"https://github.com"}
total_size=0

# "<org>/<repo>:<local dir>" pairs, overridable via $SCOOP_REPOS
DEFAULT_REPOS=(
	"ScoopInstaller/Scoop:scoop"
	"ScoopInstaller/Main:main"
	"ScoopInstaller/Extras:extras"
	"ScoopInstaller/Java:java"
	"ScoopInstaller/Nirsoft:nirsoft"
	"ScoopInstaller/Nonportable:nonportable"
	"ScoopInstaller/PHP:php"
	"ScoopInstaller/Versions:versions"
	"matthewjberger/scoop-nerd-fonts:scoop-nerd-fonts"
	"Calinou/scoop-games:scoop-games"
	"niheaven/scoop-sysinternals:scoop-sysinternals"
)
repos=(${SCOOP_REPOS:-${DEFAULT_REPOS[@]}})

failed_repos=()
for entry in "${repos[@]}"; do
	repo="${entry%%:*}"
	dir="${entry##*:}"
	if [[ ! -d "$TUNASYNC_WORKING_DIR/${dir}.git" ]]; then
		echo "Initializing ${dir}.git"
		if ! repo_init "${UPSTREAM_BASE}/${repo}.git" "$TUNASYNC_WORKING_DIR/${dir}.git"; then
			failed_repos+=("${dir}.git")
			continue
		fi
	fi
	if ! update_git "${UPSTREAM_BASE}/${repo}.git" "$TUNASYNC_WORKING_DIR/${dir}.git"; then
		failed_repos+=("${dir}.git")
	fi
done

echo "Total size is" $(numfmt --to=iec $total_size)

# Propagate failures: a partially synced mirror must not be recorded as a
# successful tunasync job.
if [[ ${#failed_repos[@]} -gt 0 ]]; then
	echo "ERROR: failed to sync: ${failed_repos[*]}" >&2
	exit 1
fi
