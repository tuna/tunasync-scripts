#!/bin/bash
# Mirror Seafile client downloads from seafile.com/download.
#
# The official download page embeds direct download links on
# package.seafile.com (Alibaba ESA CDN in front of Aliyun OSS).
# This script fetches the page with wget, parses out the download URLs with
# Python, downloads new/changed files atomically via wget, and removes stale
# local files (bounded by TUNASYNC_MAX_DELETE).
#
# wget is used (not curl or urllib) because the tunasync Docker bridge
# network can reach the package.seafile.com edge IPs only via wget.
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
# Pass an absolute path into Python: after cd, a relative
# TUNASYNC_WORKING_DIR would resolve against the working dir itself.
WORKDIR=$(pwd -P)

PAGE=$(mktemp -t seafile-page.XXXXXX.html)
trap 'rm -f "$PAGE"' EXIT

echo "Fetching download page via wget..."
wget -qO "$PAGE" --timeout=30 --tries=3 "$UPSTREAM" || {
    echo "ERROR: wget failed to fetch $UPSTREAM"
    exit 1
}

python3 - "$WORKDIR" "$MAX_DELETE" "$UPSTREAM" "$PAGE" <<'PY'
import sys, os, json, urllib.parse, subprocess, tempfile
from html.parser import HTMLParser

WORKDIR    = sys.argv[1]
MAX_DELETE = int(sys.argv[2])
UPSTREAM   = sys.argv[3]
PAGE       = sys.argv[4]
# The download page currently links to package.seafile.com (it previously
# used seafile-downloads.oss-cn-shanghai.aliyuncs.com).
ALLOWED_HOST = "package.seafile.com"
# Per-file {"size", "etag"} of the last successful download, so a same-size
# content change (e.g. seafile-android-latest.apk) is still picked up.
STATE_FILE = os.path.join(WORKDIR, ".seafile-download.state")

with open(PAGE, encoding="utf-8", errors="replace") as f:
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

# Leftover partial downloads from a killed run would be served publicly
# forever; remove them up front (downloads below use unique temp names).
for f in os.listdir(WORKDIR):
    fp = os.path.join(WORKDIR, f)
    if os.path.isfile(fp) and (f.endswith(".tmp") or ".tmp." in f):
        print(f"Removing leftover temp file: {f}", file=sys.stderr)
        os.remove(fp)

client_files = []
for u in parser.urls:
    full = urllib.parse.urljoin(UPSTREAM, u)
    p = urllib.parse.urlparse(full)
    if p.scheme not in ("http", "https") or p.hostname != ALLOWED_HOST:
        continue
    base = urllib.parse.unquote(p.path.rstrip("/").rsplit("/", 1)[-1])
    if not base or base in (".", "..") or "/" in base or "\\" in base or "\x00" in base:
        print(f"ERROR: refusing to use suspicious filename derived from {full!r}",
              file=sys.stderr)
        sys.exit(1)
    if "seafile-server" in base:
        continue
    client_files.append((full, base))

if not client_files:
    print("ERROR: no download links found on page", file=sys.stderr)
    sys.exit(1)

print(f"Found {len(client_files)} client download(s)", file=sys.stderr)

remote_names = set(name for _, name in client_files)

try:
    with open(STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)
except (OSError, ValueError):
    state = {}


def remote_head(url):
    """Get Content-Length and ETag using wget --spider."""
    r = subprocess.run(
        ["wget", "--spider", "--timeout=30", "--tries=1", "-S", url],
        capture_output=True, text=True)
    if r.returncode != 0:
        return None, None, r.stderr
    size = None
    etag = None
    for line in r.stderr.split("\n"):
        l = line.strip().lower()
        if l.startswith("content-length:"):
            try:
                size = int(l.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif l.startswith("etag:"):
            etag = line.split(":", 1)[1].strip()
    return size, etag, r.stderr


# Download each file atomically via wget (curl fails to reach the
# package.seafile.com edge IPs from the Docker bridge network; wget works).
new_files = []
for url, name in client_files:
    target = os.path.join(WORKDIR, name)

    remote_size, remote_etag, stderr = remote_head(url)
    if remote_size is None and remote_etag is None:
        # Some CDNs strip Content-Length on chunked or 302 responses; we still
        # need to know whether the URL itself is reachable.
        if stderr and "200 OK" not in stderr and "remote file exists" not in stderr.lower():
            print(f"ERROR: spider {url}: {stderr[-200:]}", file=sys.stderr)
            sys.exit(1)
        # Fall through; we'll download and trust wget to validate.

    # A file is fresh only when the size matches and the recorded ETag
    # matches; without a recorded ETag (first run with this script version)
    # the file is re-downloaded once to establish state.
    if os.path.exists(target):
        local_size = os.path.getsize(target)
        size_ok = remote_size is None or local_size == remote_size
        if remote_etag is not None:
            st = state.get(name) or {}
            fresh = (size_ok and st.get("size") == local_size
                     and st.get("etag") == remote_etag)
        else:
            fresh = size_ok
        if fresh:
            continue

    print(f"Downloading: {name} ({remote_size} bytes)" if remote_size is not None
          else f"Downloading: {name}", file=sys.stderr)
    # mkstemp creates the temp file with O_EXCL, so wget -O cannot be
    # redirected through a pre-planted symlink at a predictable path.
    fd, tmp = tempfile.mkstemp(dir=WORKDIR, prefix=name + ".tmp.")
    os.close(fd)
    r = subprocess.run(
        ["wget", "-q", "--timeout=30", "--tries=3", "-O", tmp, url],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR: download {url}: {r.stderr[-200:]}", file=sys.stderr)
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit(1)

    downloaded = os.path.getsize(tmp)
    if remote_size is not None and downloaded != remote_size:
        print(f"ERROR: short read for {name}: got {downloaded}, "
              f"expected {remote_size}", file=sys.stderr)
        os.remove(tmp)
        sys.exit(1)

    os.replace(tmp, target)
    state[name] = {"size": downloaded, "etag": remote_etag}
    new_files.append(name)

# Only delete stale files after all downloads succeeded so a transient
# upstream issue cannot wipe the mirror.
local_files = [f for f in os.listdir(WORKDIR)
               if os.path.isfile(os.path.join(WORKDIR, f))]
keep = remote_names | {os.path.basename(STATE_FILE)}
stale = [f for f in local_files
         if f not in keep and not f.endswith(".tmp") and ".tmp." not in f]
if len(stale) > MAX_DELETE:
    print(f"WARNING: {len(stale)} stale files exceeds MAX_DELETE ({MAX_DELETE})",
          file=sys.stderr)
    sys.exit(1)
for f in stale:
    fp = os.path.join(WORKDIR, f)
    print(f"Deleting stale: {f}", file=sys.stderr)
    os.remove(fp)

# Prune state entries for files no longer mirrored, then persist.
state = {k: v for k, v in state.items() if k in remote_names}
with open(STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(state, f)

print("Done.", file=sys.stderr)
PY
