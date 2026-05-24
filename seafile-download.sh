#!/bin/bash
# Mirror Seafile client downloads from seafile.com/download.
#
# The official download page embeds direct OSS download links.
# This script fetches the page with wget, parses out OSS URLs with Python,
# downloads new/changed files atomically via wget, and removes stale local
# files (bounded by TUNASYNC_MAX_DELETE).
#
# wget is used (not curl or urllib) because the tunasync Docker bridge
# network can reach the Seafile AWS origin only via wget.
set -euo pipefail

WORKDIR="${TUNASYNC_WORKING_DIR:-}"
UPSTREAM="${TUNASYNC_UPSTREAM_URL:-https://www.seafile.com/download/}"
MAX_DELETE="${TUNASYNC_MAX_DELETE:-50}"

if [ -z "$WORKDIR" ]; then
    echo "ERROR: TUNASYNC_WORKING_DIR not set"
    exit 2
fi

mkdir -p "$WORKDIR"
cd "$WORKDIR"

echo "Fetching download page via wget..."
wget -qO /tmp/seafile-page.html --timeout=30 --tries=3 "$UPSTREAM" || {
    echo "ERROR: wget failed to fetch $UPSTREAM"
    exit 1
}

python3 - "$WORKDIR" "$MAX_DELETE" "$UPSTREAM" <<PY
import sys, os, urllib.parse, subprocess
from html.parser import HTMLParser

WORKDIR    = sys.argv[1]
MAX_DELETE = int(sys.argv[2])
UPSTREAM   = sys.argv[3]
OSS_PREFIX = "seafile-downloads.oss-cn-shanghai.aliyuncs.com"

with open("/tmp/seafile-page.html", encoding="utf-8", errors="replace") as f:
    html = f.read()

class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.urls.append(v)

parser = LinkExtractor()
parser.feed(html)

oss_urls = []
for u in parser.urls:
    full = u if u.startswith("http") else "https://www.seafile.com" + (u if u.startswith("/") else "/" + u)
    if OSS_PREFIX in full and "seafile-server" not in full:
        oss_urls.append(full)

if not oss_urls:
    print("ERROR: no OSS download links found on page", file=sys.stderr)
    sys.exit(1)

print(f"Found {len(oss_urls)} client download(s)", file=sys.stderr)

remote_names = set()
for url in oss_urls:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    name = urllib.parse.unquote(name)
    remote_names.add(name)

# Delete stale local files not in the current remote set
local_files = [f for f in os.listdir(WORKDIR) if os.path.isfile(os.path.join(WORKDIR, f))]
stale = [f for f in local_files if f not in remote_names]
if len(stale) > MAX_DELETE:
    print(f"WARNING: {len(stale)} stale files exceeds MAX_DELETE ({MAX_DELETE})", file=sys.stderr)
    sys.exit(1)
for f in stale:
    fp = os.path.join(WORKDIR, f)
    print(f"Deleting stale: {f}", file=sys.stderr)
    os.remove(fp)

# Download each file atomically via wget (curl fails to Seafile AWS IPs
# from the Docker bridge network; wget works).
for url in oss_urls:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    name = urllib.parse.unquote(name)
    target = os.path.join(WORKDIR, name)
    tmp = target + ".tmp"

    # Check remote size with wget --spider
    r = subprocess.run(
        ["wget", "--spider", "--timeout=30", "--tries=1", "-S", url],
        capture_output=True, text=True)
    remote_size = 0
    for line in r.stderr.split("\n"):
        if "Content-Length:" in line:
            remote_size = int(line.split(":")[1].strip())
            break
    if r.returncode != 0:
        print(f"ERROR: spider {url}: {r.stderr[-200:]}", file=sys.stderr)
        sys.exit(1)

    if os.path.exists(target) and os.path.getsize(target) == remote_size:
        continue

    print(f"Downloading: {name} ({remote_size} bytes)", file=sys.stderr)
    r = subprocess.run(
        ["wget", "-q", "--timeout=30", "--tries=3", "-O", tmp, url],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR: download {url}: {r.stderr[-200:]}", file=sys.stderr)
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit(1)

    os.replace(tmp, target)

print("Done.", file=sys.stderr)
PY
