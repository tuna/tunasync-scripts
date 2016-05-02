#!/bin/bash
BANDERSNATCH=${BANDERSNATCH:-"/usr/local/bin/bandersnatch"}
CONF="/tmp/bandersnatch.conf"
INIT=${INIT:-"0"}

if [ ! -d "$TUNASYNC_WORKING_DIR" ]; then
	mkdir -p $TUNASYNC_WORKING_DIR
	INIT="1"
fi

echo "Syncing to $TUNASYNC_WORKING_DIR"

if [[ $INIT == "0" ]]; then
	cat > $CONF << EOF
[mirror]
directory = ${TUNASYNC_WORKING_DIR}
master = https://pypi.python.org
timeout = 15
workers = 10
stop-on-error = true
delete-packages = true
EOF
	/usr/bin/timeout -s INT 7200 $BANDERSNATCH -c $CONF mirror || exit 1

else
	cat > $CONF << EOF
[mirror]
directory = ${TUNASYNC_WORKING_DIR}
master = https://pypi.python.org
timeout = 15
workers = 10
stop-on-error = false
delete-packages = false
EOF

	$BANDERSNATCH -c $CONF mirror || exit 1
fi
