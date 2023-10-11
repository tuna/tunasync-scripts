#!/bin/bash
if [[ -z "$TUNASYNC_UPSTREAM_URL" ]];then
  echo "Please set the TUNASYNC_UPSTREAM_URL"
  exit 1
fi

if [[ ! -z "$RECURSIVE" ]];then
  echo "Sync in a recursive mode"
fi

TMPDIR=${TMPDIR:-"/tmp"}

MIRROR_BASE_URL=${MIRROR_BASE_URL:-"https://mirrors.tuna.tsinghua.edu.cn/git/"}
WORKING_DIR_BASE=${WORKING_DIR_BASE:-"/data/mirrors/git/"}
GENERATED_SCRIPT=${GENERATED_SCRIPT:-"/data/mirrors/git/qemu/qemu.sh"}

if [[ ! -z "$RECURSIVE" ]]; then
  echo "#!/usr/bin/env bash" > $GENERATED_SCRIPT.tmp
fi

function script_append() {
if [[ ! -z "$RECURSIVE" ]]; then
  echo "$1" >> $GENERATED_SCRIPT.tmp
fi
}

depth=0

function echon() {
  echo depth "$depth" "$@"
}

function repo_init() {
  local upstream=$1
  local working_dir=$2
  git clone --mirror "$upstream" "$working_dir"
}

function update_linux_git() {
  local upstream=$1
  local working_dir=$2
  cd "$working_dir"
  echon "==== SYNC $upstream START ===="
  git remote set-url origin "$upstream"
  "timeout" -s INT 3600 git remote -v update -p
  local ret=$?
  [[ $ret -ne 0 ]] && echon "git update failed with rc=$ret"
  local head=$(git remote show origin | awk '/HEAD branch:/ {print $NF}')
  [[ -n "$head" ]] && echo "ref: refs/heads/$head" > HEAD
  objs=$(find objects -type f | wc -l)
  [[ "$objs" -gt 8 ]] && git repack -a -b -d
  sz=$(git count-objects -v|grep -Po '(?<=size-pack: )\d+')
  total_size=$(($total_size+1024*$sz))
  echon "==== SYNC $upstream DONE ===="
  return $ret
}

function git_sync() {
  local upstream=$1
  local working_dir=$2
  if [[ ! -f "$working_dir/HEAD" ]]; then
    echon "Initializing $upstream mirror"
    repo_init "$upstream" "$working_dir"
    return $?
  fi
  update_linux_git "$upstream" "$working_dir"
}

function checkout_repo() {
  local repo_dir="$1"
  local work_tree="$2"
  local commit="$3"

  if [[ -z "$commit" ]]; then
    commit="HEAD"
  fi
  echon "Considering $repo_dir on commit $commit"
  local commit_obj_type=$(git -C "$repo_dir" cat-file -t "$commit")
  local rc=$?
  if [[ $rc -ne 0 ]] || [[ "$commit_obj_type" != "commit" ]]; then
    echon "Commit $commit is not a valid commit object"
    return 1
  fi
  local repo_dir_no_git=${repo_dir%%.git}
  if git -C "$repo_dir" cat-file -e "$commit:.gitmodules" 2>/dev/null; then
    echon "Find submodules for $repo_dir"
    local -a submodules
    IFS= readarray -d '' submodules < <(
      git -C "$repo_dir" config --null --blob "$commit:.gitmodules" --name-only --get-regexp "^submodule\." | sed --null-data 's/\.[^.]*$//' | sort --zero-terminated --unique
    )
    for submoudle in "${submodules[@]}"; do
      local submodule_path=$(git -C "$repo_dir" config --blob "$commit:.gitmodules" --get "$submoudle.path")
      local submodule_url=$(git -C "$repo_dir" config --blob "$commit:.gitmodules" --get "$submoudle.url")
      if [[ -z "$submodule_path" ]] || [[ -z "$submodule_url" ]]; then
        continue
      fi
      local submodule_path_parent=$(dirname -- "$submodule_path")
      if [[ "$submodule_path_parent" = "." ]]; then
        submodule_path_parent=""
      fi
      local submodule_commit=$(git -C "$repo_dir" ls-tree -d -z --format="%(path)/%(objectname)" "$commit:$submodule_path_parent" | fgrep --null-data "$(basename -- "$submodule_path")/" | head --zero-terminated --lines 1 | cut -d '/' -f 2 | tr -d '\0' )
      if [[ -z "$submodule_commit" ]]; then
        echon "Cannot find submodule commit for $submodule_path"
        continue
      fi
      local submodule_git_path="$repo_dir_no_git/$submodule_path.git"
      mkdir -p -- "$submodule_git_path"
      local submodule_mirror_url=$(echo "$submodule_git_path" | sed "s#$WORKING_DIR_BASE#$MIRROR_BASE_URL#")
      script_append "cat >>.git/config <<EOF"
      script_append "[submodule \"$submodule_path\"]"
      script_append "	active = true"
      script_append "	url = $submodule_mirror_url"
      script_append "EOF"
      script_append "mkdir -p ${submodule_path@Q}"
      script_append "git clone ${submodule_mirror_url@Q} ${submodule_path@Q}"
      script_append "git submodule init ${submodule_path@Q}"
      script_append "git submodule update ${submodule_path@Q}"
      script_append "pushd ${submodule_path@Q}"
      git_sync_recursive "$submodule_url" "$submodule_git_path" "$submodule_commit"
      script_append "popd"
    done
  fi
}

function git_sync_recursive() {
  depth=$(($depth+1))
  local upstream=$1
  local working_dir=$2
  # it is ok that commit=""
  local commit=$3
  git_sync "$upstream" "$working_dir"
  local ret=$?
  if [[ $ret -ne 0 ]]; then
    echon "git sync failed with rc=$ret"
    return $ret
  fi

  if [[ ! -z "$RECURSIVE" ]]; then
    working_dir_name=$(basename -- "$working_dir")
    working_dir_name_no_git=${working_dir_name%%.git}
    checkout_repo "$working_dir" "$TMPDIR/$working_dir_name_no_git" "$commit"
  fi
  depth=$(($depth-1))
}

path=$(basename -- "$TUNASYNC_WORKING_DIR")
path_no_git=${path%%.git}
mirror_url=$(echo "$TUNASYNC_WORKING_DIR" | sed "s#$WORKING_DIR_BASE#$MIRROR_BASE_URL#")
script_append "mkdir -p ${path_no_git@Q}"
script_append "git clone ${mirror_url@Q} ${path_no_git@Q}"
script_append "pushd ${path_no_git@Q}"
git_sync_recursive "$TUNASYNC_UPSTREAM_URL" "$TUNASYNC_WORKING_DIR"
script_append "git submodule absorbgitdirs"
script_append "popd"

if [[ ! -z "$RECURSIVE" ]]; then
  mv -- "$GENERATED_SCRIPT.tmp" "$GENERATED_SCRIPT"
fi

echo "Total size is" $(numfmt --to=iec "$total_size")
