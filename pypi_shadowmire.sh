#!/bin/bash

set -e

SHADOWMIRE=${SHADOWMIRE:-"/home/scripts/shadowmire"}
PYPI_MASTER="https://pypi.org"

TUNASYNC_UPSTREAM=${TUNASYNC_UPSTREAM_URL:-$PYPI_MASTER}
TUNASYNC_UPSTREAM=${TUNASYNC_UPSTREAM%/}

CONF="/tmp/shadowmire.conf"
INIT=${INIT:-"0"}
SHADOWMIRE_UPSTREAM=${SHADOWMIRE_UPSTREAM:-"0"}

if [ ! -d "$TUNASYNC_WORKING_DIR" ]; then
	mkdir -p $TUNASYNC_WORKING_DIR
	INIT="1"
fi

export REPO="${TUNASYNC_WORKING_DIR}"

echo "Syncing to $TUNASYNC_WORKING_DIR"

DOWNLOAD_MIRROR=""
if [[ $TUNASYNC_UPSTREAM != $PYPI_MASTER ]]; then
    # see https://github.com/pypa/bandersnatch/pull/928 for more info
    DOWNLOAD_MIRROR="shadowmire_upstream = ${TUNASYNC_UPSTREAM}"
fi

(
cat << EOF
[options]
sync_packages = true
${DOWNLOAD_MIRROR}
exclude = [
    ".+-nightly(-|$)",
EOF

for i in $PYPI_EXCLUDE; do
    echo "    \"$i\","
done

cat << EOF
]
EOF

cat << EOF
]
prerelease_exclude = [
    "duckdb",
    "graphscope-client",
    "lalsuite",
    "gs-(apps|engine|include)",
    "bigdl-dllib(-spark2|-spark3)?",
    "ovito"
]
EOF
) > $CONF

echo "Generated config file:"
cat $CONF

exec $SHADOWMIRE --config $CONF sync
