#!/bin/bash
UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://gerrit.googlesource.com/git-repo"}

function repo_init() {
	git clone --mirror $UPSTREAM $TUNASYNC_WORKING_DIR
}

function update_repo_git() {
	cd $TUNASYNC_WORKING_DIR
	echo "==== SYNC repo.git START ===="
	git remote set-url origin "$UPSTREAM"
	/usr/bin/timeout -s INT 3600 git remote -v update -p
	head=$(git remote show origin | awk '/HEAD branch:/ {print $NF}')
	[[ -n "$head" ]] && echo "ref: refs/heads/$head" > HEAD
	git repack -a -b -d
	sz=$(git count-objects -v|grep -Po '(?<=size-pack: )\d+')
	sz=$(($sz*1024))
	echo "Total size is" $(numfmt --to=iec $sz)
	echo "==== SYNC repo.git DONE ===="
}

function checkout_repo() {
    git -C $TUNASYNC_WORKING_DIR show HEAD:repo > $TUNASYNC_WORKING_DIR/git-repo
}

# ---------------------------------------
# 20220511 Add Function for Initing git-remote-hg Script
# 2022 (C) LinuxBCKP
# ---------------------------------------
function init_git_remote_hg() {
    mkdir /usr/bin
    curl -o /usr/bin/git-remote-hg https://raw.githubusercontent.com/fingolfin/git-remote-hg/master/git-remote-hg
    chmod +x /usr/bin/git-remote-hg
    echo 'export PATH=/usr/bin:$PATH' >> ~/.bashrc
    source ~/.bashrc
    git config --global core.notesRef refs/notes/hg
}

# ---------------------------------------
# 20220511 Add Function for Initing Mercurial Mirror
# 2022 (C) LinuxBCKP
# ---------------------------------------
function repo_init_hg() {
        HGUPSTREAM="hg::"${UPSTREAM}
	git clone --mirror $HGUPSTREAM $TUNASYNC_WORKING_DIR
}

# ---------------------------------------
# 20220511 Add Function for Updating Mercurial Mirror
# 2022 (C) LinuxBCKP
# ---------------------------------------
function update_repo_git_hg() {
        HGUPSTREAM="hg::"${UPSTREAM}
	cd $TUNASYNC_WORKING_DIR
	echo "==== SYNC repo.git START ===="
	git remote set-url origin "$HGUPSTREAM"
	/usr/bin/timeout -s INT 3600 git remote -v update -p
	head=$(git remote show origin | awk '/HEAD branch:/ {print $NF}')
	[[ -n "$head" ]] && echo "ref: refs/heads/$head" > HEAD
	git repack -a -b -d
	sz=$(git count-objects -v|grep -Po '(?<=size-pack: )\d+')
	sz=$(($sz*1024))
	echo "Total size is" $(numfmt --to=iec $sz)
	echo "==== SYNC repo.git DONE ===="
}

if [[ ! -f "$TUNASYNC_WORKING_DIR/HEAD" ]]; then
	echo "Initializing repo.git mirror"
	repo_init
fi

update_repo_git
checkout_repo
