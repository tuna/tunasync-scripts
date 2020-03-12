#!/bin/bash
# requires: curl, unzip, gsutil, jq

DEST_DIR="${TUNASYNC_WORKING_DIR}"
SYNC_FLUTTER_ENGINES=latest_tags

gsutil rsync -d -C -r -x '(1\..+/|\d{5}/|.+/api-docs)' gs://dart-archive/channels/stable/release \
    "${DEST_DIR}/dart-archive/channels/stable/release"
gsutil rsync -d -C -r -x '(dev|beta)' gs://flutter_infra/releases \
    "${DEST_DIR}/flutter_infra/releases"


function sync_engine() {
    [[ -z "$1" ]] && exit 1
    path="flutter_infra/flutter/$1"
    mkdir -p "${DEST_DIR}/$path" 2>/dev/null || true
    gsutil -m rsync -d -C -r "gs://$path" "${DEST_DIR}/$path"
}

if [[ "$SYNC_FLUTTER_ENGINES" == "recent_tags" ]]; then
    curl -H "Authorization: token $GITHUB_TOKEN" "https://api.github.com/repos/flutter/flutter/tags" | \
        jq -r '.[]| [.name]| @tsv' | \
        while IFS=$'\t' read -r name; do
            engine_version=$(curl "https://raw.githubusercontent.com/flutter/flutter/$name/bin/internal/engine.version")
            echo "======== tag $name, engine version ($engine_version) ========"
            sync_engine "$engine_version"
        done
elif [[ "$SYNC_FLUTTER_ENGINES" == "latest_tags" ]]; then
    for branch in stable beta dev; do
        engine_version=$(curl "https://raw.githubusercontent.com/flutter/flutter/$branch/bin/internal/engine.version")
        echo "======== branch ${branch}, engine version ($engine_version) ========"
        sync_engine "$engine_version"

        for i in ${DEST_DIR}/flutter_infra/releases/${branch}/macos/*.zip; do
            [[ -f "$i" ]] || continue
            engine_version=$(unzip -p "$i" flutter/bin/internal/engine.version)
            echo "======== installer name ${i##*/}, engine version ($engine_version) ========"
            sync_engine "$engine_version"
        done
    done
fi

for path in "flutter_infra/ios-usb-dependencies" \
            "flutter_infra/flutter/fonts" \
            "flutter_infra/gradle-wrapper"
do
    mkdir -p "${DEST_DIR}/$path" 2>/dev/null || true
    gsutil rsync -d -C -r "gs://$path" "${DEST_DIR}/$path"
done