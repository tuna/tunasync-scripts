#!/bin/bash
GEM=${GEM:-"gem"}
export HOME="/tmp/rubygems"
CONF="$HOME/.gem/.mirrorrc"

mkdir -p "$HOME/.gem"

INIT=${INIT:-"0"}
BUSYBOX=${BUSYBOX:-"0"}

if [ ! -d "$TUNASYNC_WORKING_DIR" ]; then
	mkdir -p $TUNASYNC_WORKING_DIR
	INIT="1"
fi

echo "Syncing to $TUNASYNC_WORKING_DIR"

cat > $CONF << EOF
---
- from: https://rubygems.org
  to: ${TUNASYNC_WORKING_DIR}
  parallelism: 10
  retries: 2
  delete: true
  skiperror: true
EOF

if [[ $INIT == "0" ]]; then
	if [[ $BUSYBOX == "0" ]]; then
		timeout -s INT 7200 $GEM mirror -V
	else
		timeout -t 7200 -s INT $GEM mirror -V
	fi
else
	$GEM mirror -V
fi

ret=$?
if [[ $ret == 124 ]]; then
	echo 'Sync timeout (/_\\)'
fi

exit $ret
