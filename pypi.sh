#!/bin/bash
BANDERSNATCH=${BANDERSNATCH:-"/usr/local/bin/bandersnatch"}
TUNASYNC_UPSTREAM=${TUNASYNC_UPSTREAM:-"https://pypi.org/"}
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
master = ${TUNASYNC_UPSTREAM}
json = true
timeout = 15
workers = 10
hash-index = false
stop-on-error = false
delete-packages = true
EOF
	/usr/bin/timeout -s INT 36000 $BANDERSNATCH -c $CONF mirror 
	if [[ $? == 124 ]]; then
		echo 'Sync timeout (/_\\)'
		exit 1
	fi
else
	cat > $CONF << EOF
[mirror]
directory = ${TUNASYNC_WORKING_DIR}
master = ${TUNASYNC_UPSTREAM}
json = true
timeout = 15
workers = 10
hash-index = false
stop-on-error = false
delete-packages = false
EOF

	$BANDERSNATCH -c $CONF mirror
fi

TODOFILE="${TUNASYNC_WORKING_DIR}/todo"
if [[ -f $TODOFILE ]]; then
	rsize=`stat -c "%s" ${TODOFILE}`
	if [[ "$rsize" != "0" ]]; then
		echo "Sync Failed T_T"
		exit 1
	fi
fi

echo "Sync Done ^_-"
exit 0
