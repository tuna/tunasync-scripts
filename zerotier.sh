#!/bin/bash
mkdir -p "$TUNASYNC_WORKING_DIR"
wget --mirror \
     --no-parent \
     --no-host-directories \
     --cut-dirs=1 \
     --relative \
     --recursive \
     --level=inf \
     --accept="*" \
     --reject="index.html*,*.deb,*.rpm" \
     --reject-regex=".*/debian/.*|.*/redhat/.*" \
     --exclude-directories="*/*" \
     --quiet \
     --continue \
     --directory-prefix="$TUNASYNC_WORKING_DIR" \
     "$TUNASYNC_UPSTREAM_URL"
exit_code=$?
if [ $exit_code -ne 0 ] && [ $exit_code -ne 8 ]; then
    echo "Error: wget synchronization failed with exit code: $exit_code"
    exit 1
fi
total_size=$(du -shL "$TUNASYNC_WORKING_DIR" | cut -f1)
echo "Total size is $total_size"
