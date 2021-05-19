#!/bin/bash
set -e

_here=`dirname $(realpath $0)`
apt_sync="${_here}/apt-sync.py" 

WORKING_DIR="${TUNASYNC_WORKING_DIR}"
export REPO_SIZE_FILE=/tmp/reposize.$RANDOM

ARCH_LIST="aarch64,arm,i686,x86_64"

"$apt_sync" --delete "https://cf-ipfs.com/ipns/k51qzi5uqu5dg9vawh923wejqffxiu9bhqlze5f508msk0h7ylpac27fdgaskx" stable main    $ARCH_LIST "${WORKING_DIR}/termux-packages-24"
"$apt_sync" --delete "https://cf-ipfs.com/ipns/k51qzi5uqu5dj05z8mr958kwvrg7a0wqouj5nnoo5uqu1btnsljvpznfaav9nk" unstable main  $ARCH_LIST "${WORKING_DIR}/unstable-packages"
"$apt_sync" --delete "https://cf-ipfs.com/ipns/k51qzi5uqu5dgu3homski160l4t4bmp52vb6dbgxb5bda90rewnwg64wnkwxj4" x11 main       $ARCH_LIST "${WORKING_DIR}/x11-packages"
"$apt_sync" --delete "https://cf-ipfs.com/ipns/k51qzi5uqu5dhvbtvdf46kkhobzgamhiirte6s6k28l2c1iapumphh3cpkw33f" science stable $ARCH_LIST "${WORKING_DIR}/science-packages-24"
"$apt_sync" --delete "https://cf-ipfs.com/ipns/k51qzi5uqu5dhngjg68o8x9uimwy5h8iqt91n2266idc7uet9ew3lc472upy27" games stable   $ARCH_LIST "${WORKING_DIR}/game-packages-24"
"$apt_sync" --delete "https://cf-ipfs.com/ipns/k51qzi5uqu5dlp5yjlahzcp3kfpnhbifo9ka9iybo3bp5vt781duafkyyvt9al" root stable    $ARCH_LIST "${WORKING_DIR}/termux-root-packages-24"

echo "finished"

"${_here}/helpers/size-sum.sh" $REPO_SIZE_FILE --rm
