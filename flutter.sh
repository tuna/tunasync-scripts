#!/bin/bash
# requires: curl, unzip, gsutil, jq

DEST_DIR="${TUNASYNC_WORKING_DIR}"
SYNC_FLUTTER_ENGINES=latest_tags
FLUTTER_INFRA_BUCKET=flutter_infra_release

mkdir "${DEST_DIR}/dart-archive/channels/stable/release" \
    "${DEST_DIR}/${FLUTTER_INFRA_BUCKET}/releases" \
    2>/dev/null || true

gsutil rsync -d -C -r -x '(1\..+/|\d{5}/|.+/api-docs)' gs://dart-archive/channels/stable/release \
    "${DEST_DIR}/dart-archive/channels/stable/release"
gsutil rsync -d -C -r -x '(dev|beta)' gs://${FLUTTER_INFRA_BUCKET}/releases \
    "${DEST_DIR}/${FLUTTER_INFRA_BUCKET}/releases"

cur_engine_list=/tmp/cur_engine_list.txt
>$cur_engine_list

function sync_engine() {
    [[ -z "$1" ]] && exit 1
    echo $1 >>$cur_engine_list
    path="${FLUTTER_INFRA_BUCKET}/flutter/$1"
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

        for i in ${DEST_DIR}/${FLUTTER_INFRA_BUCKET}/releases/${branch}/macos/*.zip; do
            [[ -f "$i" ]] || continue
            engine_version=$(unzip -p "$i" flutter/bin/internal/engine.version)
            echo "======== installer name ${i##*/}, engine version ($engine_version) ========"
            sync_engine "$engine_version"
        done
    done
fi

#cat $cur_engine_list
find ${DEST_DIR}/${FLUTTER_INFRA_BUCKET}/flutter -maxdepth 1 -mindepth 1 -mtime +90 | while read line; do
    # $line looks like '/xxx/flutter/flutter_infra_release/flutter/ca7623eb39d74a8cbdd095fcc7db398267b6928f'
    version=${line##*/}
    grep --quiet "$version" "$cur_engine_list" || ( echo "Removing $line"; rm -rf "$line" )
done


for path in "${FLUTTER_INFRA_BUCKET}/ios-usb-dependencies" \
            "${FLUTTER_INFRA_BUCKET}/flutter/fonts" \
            "${FLUTTER_INFRA_BUCKET}/gradle-wrapper" \
            "download.flutter.io"
do
    mkdir -p "${DEST_DIR}/$path" 2>/dev/null || true
    gsutil rsync -d -C -r "gs://$path" "${DEST_DIR}/$path"
done
