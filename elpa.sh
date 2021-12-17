#!/bin/bash
# requires: rsync lftp

set -e
set -o pipefail

RSYNC_OPTS="-aHvh --no-o --no-g --stats --exclude .~tmp~/ --delete --delete-excluded --delete-after --delay-updates --safe-links --timeout=120 --contimeout=120"

USE_IPV6=${USE_IPV6:-"0"}
if [[ $USE_IPV6 == "1" ]]; then
	RSYNC_OPTS="-6 ${RSYNC_OPTS}"
fi

UPSTREAMS=(
  "rsync://elpa.gnu.org/elpa/"
  "rsync://elpa.nongnu.org/nongnu/"
  "rsync://melpa.org/packages/"
  "rsync://stable.melpa.org/packages/"
  )

REPOS=(
  "gnu"
  "nongnu"
  "melpa"
  "stable-melpa"
  )

for I in ${!UPSTREAMS[@]}; do
  upstream=${UPSTREAMS[$I]}
  repo=${REPOS[$I]}

  dest=${TUNASYNC_WORKING_DIR}/${repo}
  [ ! -d "$dest" ] && mkdir -p "$dest"

  rsync ${RSYNC_OPTS} "$upstream" "$dest"
done

org() {
  dest=${TUNASYNC_WORKING_DIR}/org
  [ ! -d "$dest" ] && mkdir -p "$dest"
  cd $dest

  lftp "https://orgmode.org/elpa/" -e 'mirror -v -P 5 --delete --no-recursion; bye'
}
org
