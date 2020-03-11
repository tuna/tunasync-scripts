#!/bin/bash
# requires: curl, unzip, gsutil, jq

DEST_DIR="${TUNASYNC_WORKING_DIR}"
STABLE_VERSION_ENGINE=true

gsutil rsync -d -C -r -x '(1\..+/|\d{5}/|.+/api-docs)' gs://dart-archive/channels/stable/release \
    "${DEST_DIR}/dart-archive/channels/stable/release"
gsutil rsync -d -C -r -x '(dev|beta)' gs://flutter_infra/releases \
    "${DEST_DIR}/flutter_infra/releases"


if [[ "$STABLE_VERSION_ENGINE" == "true" ]];then
    for i in ${DEST_DIR}/flutter_infra/releases/stable/macos/*.zip; do
        engine_version=$(unzip -p "$i" flutter/bin/internal/engine.version)
        echo "======== name ${i##*/}, engine version ($engine_version) ========"
        path=flutter_infra/flutter/$engine_version
        mkdir -p "${DEST_DIR}/$path" 2>/dev/null || true
        gsutil -m rsync -d -C -r "gs://$path" "${DEST_DIR}/$path"
    done
else
    curl -H "Authorization: token $GITHUB_TOKEN" "https://api.github.com/repos/flutter/flutter/tags" | \
        jq -r '.[]| [.name]| @tsv' | \
        while IFS=$'\t' read -r name; do
            engine_version=$(curl "https://raw.githubusercontent.com/flutter/flutter/$name/bin/internal/engine.version")
            echo "======== tag $name, engine version ($engine_version) ========"
            path=flutter_infra/flutter/$engine_version
            mkdir -p "${DEST_DIR}/$path" 2>/dev/null || true
            gsutil -m rsync -d -C -r "gs://$path" "${DEST_DIR}/$path"
        done
fi

exit 0

for path in "flutter_infra/ios-usb-dependencies" \
            "flutter_infra/flutter/fonts" \
            "flutter_infra/gradle-wrapper"
do
    mkdir -p "${DEST_DIR}/$path" 2>/dev/null || true
    gsutil rsync -d -C -r "gs://$path" "${DEST_DIR}/$path"
done