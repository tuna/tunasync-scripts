#!/bin/bash
set -e
BANDERSNATCH=${BANDERSNATCH:-"/usr/local/bin/bandersnatch"}
PYPI_MASTER="https://pypi.org"
TUNASYNC_UPSTREAM=${TUNASYNC_UPSTREAM_URL:-$PYPI_MASTER}
TUNASYNC_UPSTREAM=${TUNASYNC_UPSTREAM%/}
CONF="/tmp/bandersnatch.conf"
INIT=${INIT:-"0"}

if [ ! -d "$TUNASYNC_WORKING_DIR" ]; then
	mkdir -p $TUNASYNC_WORKING_DIR
	INIT="1"
fi

echo "Syncing to $TUNASYNC_WORKING_DIR"

DOWNLOAD_MIRROR=""
if [[ $TUNASYNC_UPSTREAM != $PYPI_MASTER ]]; then
    # see https://github.com/pypa/bandersnatch/pull/928 for more info
    DOWNLOAD_MIRROR="download-mirror = ${TUNASYNC_UPSTREAM}"
fi

if [[ $INIT == "0" ]]; then
(
	cat << EOF
[mirror]
directory = ${TUNASYNC_WORKING_DIR}
storage-backend = filesystem
master = ${PYPI_MASTER}
${DOWNLOAD_MIRROR}
json = true
timeout = 300
workers = 5
hash-index = false
stop-on-error = false
delete-packages = true
compare-method = stat

[plugins]
enabled =
    regex_project
    blocklist_project
    prerelease_release

[filter_regex]
packages =
    .+-nightly(-|$)

[filter_prerelease]
packages =
    duckdb
    graphscope-client
    lalsuite
    gs-apps
    gs-engine
    gs-include
    bigdl-dllib
    bigdl-dllib-spark2
    bigdl-dllib-spark3
    ovito

[blocklist]
packages =
    uselesscapitalquiz
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
master = ${PYPI_MASTER}
${DOWNLOAD_MIRROR}
json = true
timeout = 15
workers = 10
hash-index = false
stop-on-error = false
delete-packages = false
EOF

	exec $BANDERSNATCH -c $CONF mirror
fi

