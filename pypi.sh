#!/bin/bash
set -e
BANDERSNATCH=${BANDERSNATCH:-"/usr/local/bin/bandersnatch"}
TUNASYNC_UPSTREAM=${TUNASYNC_UPSTREAM_URL:-"https://pypi.org/"}
CONF="/tmp/bandersnatch.conf"
INIT=${INIT:-"0"}

if [ ! -d "$TUNASYNC_WORKING_DIR" ]; then
	mkdir -p $TUNASYNC_WORKING_DIR
	INIT="1"
fi

echo "Syncing to $TUNASYNC_WORKING_DIR"

if [[ $INIT == "0" ]]; then
(
	cat << EOF
[mirror]
directory = ${TUNASYNC_WORKING_DIR}
master = ${TUNASYNC_UPSTREAM}
json = true
timeout = 300
workers = 5
hash-index = false
stop-on-error = false
delete-packages = true
compare-method = stat

[plugins]
enabled =
    blocklist_project

[blocklist]
packages =
    tf-nightly-gpu
    tf-nightly
    tensorflow-io-nightly
    tf-nightly-cpu
    pyagrum-nightly
EOF
	for i in $PYPI_EXCLUDE; do
		echo "    $i"
	done
) > $CONF
	exec $BANDERSNATCH -c $CONF mirror 
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

	exec $BANDERSNATCH -c $CONF mirror
fi

