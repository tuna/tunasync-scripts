#!/bin/bash
GEM=${GEM:-"gem"}
export HOME="/tmp/rubygems"
CONF="$HOME/.gem/.mirrorrc"

mkdir -p "$HOME/.gem"

INIT=${INIT:-"0"}

if [ ! -d "$TUNASYNC_WORKING_DIR" ]; then
	mkdir -p $TUNASYNC_WORKING_DIR
	INIT="1"
fi

echo "Syncing to $TUNASYNC_WORKING_DIR"

if [[ $INIT == "0" ]]; then

	cat > $CONF << EOF
---
- from: https://rubygems.org
  to: ${TUNASYNC_WORKING_DIR}
  parallelism: 10
  retries: 2
  delete: true
  skiperror: true
EOF

	/usr/bin/timeout -s INT 7200 $GEM mirror  
	if [[ $? == 124 ]]; then
		echo 'Sync timeout (/_\\)'
		exit 1
	fi

else

	cat > $CONF << EOF
---
- from: https://rubygems.org
  to: ${TUNASYNC_WORKING_DIR}
  parallelism: 10
  retries: 2
  delete: true
  skiperror: true
EOF

	$GEM mirror

fi
