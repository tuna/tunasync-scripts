#!/bin/sh

set -eu

image="${1:?usage: $0 IMAGE}"
runtime="${CONTAINER_RUNTIME:-docker}"
repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

"$runtime" run --rm --volume "$repo_dir:/src:ro" "$image" sh -eu -c '
    python3 -c "import aiohttp, click, OpenSSL, requests, socks, tqdm, yaml; from pyquery import PyQuery as pq"
    python3 /src/shadowmire.py --help >/dev/null
    python3 /src/docker-ce.py --help >/dev/null
    command -v gsutil
    gsutil version -l >/dev/null
'
