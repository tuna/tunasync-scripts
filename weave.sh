#!/bin/bash
set -e

GIT=${GIT:-"/bin/repo"}
USE_BITMAP_INDEX=${USE_BITMAP_INDEX:-"0"}
MANIFEST_URL=$TUNASYNC_UPSTREAM_URL/weave/manifest
MANIFEST_DIR=$TUNASYNC_WORKING_DIR/.manifest
MANIFEST_XML_REPOLIST=$(dirname $0)/helpers/manifest-xml-repolist.py
IGNORED_REPO=(
    "weave/tests"  # this is a private repo
)

export GIT_TERMINAL_PROMPT=0

function contains() {
    for e in "${@:2}"; do [[ "$e" == "$1" ]] && return 0; done
    return 1
}

function git_clone_or_pull {
    URL=$1
    DIRECTORY=$2
    MIRROR=$3
    if [[ -z $MIRROR ]]; then
        if [[ -d $DIRECTORY ]]; then
            git -C $DIRECTORY pull
        else
            git clone $URL $DIRECTORY 
        fi
    else
        if [[ -d $DIRECTORY ]]; then
            git -C $DIRECTORY remote update
        else
            git clone --mirror $URL $DIRECTORY 
        fi
    fi
}

function git_repack() {
	echo "Start writing bitmap index"
	while read repo; do 
        echo $repo
		cd $repo
		size=$(du -sm .|cut -f1)
		if [[ "$size" -gt "100" ]]; then
			echo $repo, ${size}M
			git repack -a -b -d
		fi
	done < <(find $TUNASYNC_WORKING_DIR -not -path "$MANIFEST_DIR/.git/*" -type f -name HEAD -exec dirname '{}' ';')
}

git_clone_or_pull $MANIFEST_URL $MANIFEST_DIR

for repo in $($MANIFEST_XML_REPOLIST $MANIFEST_DIR/default.xml weave); do
    contains $repo ${IGNORED_REPO[@]} && continue
    git_clone_or_pull $TUNASYNC_UPSTREAM_URL/$repo $TUNASYNC_WORKING_DIR/$repo yes
done

if [[ "$USE_BITMAP_INDEX" == "1" ]]; then
	git_repack
fi
