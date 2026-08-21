#!/bin/bash
set -euo pipefail

# Proxmox is intentionally not handled as a single root-level tsumugu sync.
#
# Why this custom wrapper exists:
#   * download.proxmox.com has a normal nginx-style tree for /debian/ and /images/.
#   * /iso/ is NOT a normal directory index. It is a custom HTML download page
#     with product cards, buttons, and an external https://www.proxmox.com link.
#   * tsumugu's nginx/apache/directory-lister parsers do not parse /iso/ safely.
#   * tsumugu's fallback parser can discover /iso/ links, but in the current
#     deployed version it reports ISO file sizes as 0 in list output and is much
#     slower/less deterministic for production use.
#   * Running tsumugu from the repository root with --exclude '^/iso/' is unsafe:
#     excluded remote paths are still treated as stale local paths during cleanup,
#     so an existing local /iso/ directory can be deleted.
#   * Using --no-delete globally would protect /iso/, but would also stop cleanup
#     for stale files under /debian/ and /images/, which is not acceptable.
#
# The safe design is therefore:
#   1. Let tsumugu fully own only the subtrees it can parse safely: /debian/ and
#      /images/. Cleanup is still enabled inside those subtrees.
#   2. Handle /iso/ with a small purpose-built HTML link parser that performs
#      HEAD checks, downloads to .tmp.* files, atomically replaces completed
#      files, and deletes stale /iso/ files only within a bounded max-delete.
#
# If a future maintainer wants to remove this script, first prove with an
# isolated two-run test that tsumugu can parse /iso/, skip existing large ISO
# files correctly, and avoid deleting unrelated local data.

UPSTREAM=${TUNASYNC_UPSTREAM_URL:-http://download.proxmox.com/}
WORKDIR=${TUNASYNC_WORKING_DIR:?TUNASYNC_WORKING_DIR is required}
THREADS=${TUNASYNC_TSUMUGU_THREADS:-1}
MAXDELETE=${TUNASYNC_TSUMUGU_MAXDELETE:-10000}
USERAGENT=${TUNASYNC_TSUMUGU_USERAGENT:-"tsumugu/$(tsumugu --version | tail -n1 | cut -d' ' -f2)"}
export TUNASYNC_TSUMUGU_USERAGENT="$USERAGENT"
export NO_COLOR=1

mkdir -p "$WORKDIR"
cd "$WORKDIR"

# Sync one nginx-indexed subtree into its matching local subdirectory.
#
# IMPORTANT: The local workdir passed to tsumugu is "$WORKDIR/$name", not the
# repository root. This confines tsumugu's cleanup/deletion logic to that
# subtree. It must not be changed back to "$WORKDIR" unless /iso/ deletion has
# been proven safe again.
sync_subtree() {
  local name="$1"
  shift
  mkdir -p "$WORKDIR/$name"
  tsumugu sync \
    --timezone 0 \
    --user-agent "$USERAGENT" \
    --max-delete "$MAXDELETE" \
    --parser nginx \
    --threads "$THREADS" \
    "$@" \
    "${UPSTREAM%/}/$name/" "$WORKDIR/$name"
}

# The Debian repository has a few upstream directories that are present in the
# HTML index but return 401 when listed. Exclude only those known-bad leaves,
# plus changelog files already excluded by the historical Proxmox config.
sync_subtree debian \
  --exclude '/devel/dists/.+changelog$' \
  --exclude '/pmg/dists/.+changelog$' \
  --exclude '^/dists/trixie/pve-test/binary-arm64/' \
  --exclude '^/pve/dists/trixie/pve-test/binary-arm64/'

# /images/ is a normal nginx-indexed subtree and can be fully owned by tsumugu.
sync_subtree images

python3 - <<'PY'
import email.utils
import html.parser
import os
import re
import shutil
import socket
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# /iso/ custom sync stage
# ------------------------
# The official page http://download.proxmox.com/iso/ is a custom HTML page.
# It currently contains one external link to https://www.proxmox.com plus one
# same-host link for every published ISO-side artifact (*.iso, *.torrent,
# *.sha256, *.asc). We intentionally accept only same-host /iso/ links and
# conservative filenames, so a layout change or unexpected external link cannot
# cause arbitrary downloads.
#
# Completeness model:
#   * remote_names is derived from the official /iso/ page's same-host links.
#   * each remote file is HEADed to obtain Content-Length and Last-Modified.
#   * existing local files with matching size are kept and their mtime updated.
#   * changed/missing files are downloaded to .tmp.<name> first, then atomically
#     renamed into place.
#   * stale local files under /iso/ are removed only after all remote links have
#     been processed, and only if the count is <= TUNASYNC_PROXMOX_ISO_MAXDELETE.
#
# This stage deliberately does not verify SHA256 itself; however the mirror was
# separately reviewed after implementation and all official *.sha256 files
# matched their local *.iso payloads. Future reviews can repeat that check.
socket.setdefaulttimeout(60)
base = os.environ.get('TUNASYNC_UPSTREAM_URL', 'http://download.proxmox.com/').rstrip('/') + '/iso/'
allowed_netloc = urllib.parse.urlparse(base).netloc
work = Path(os.environ['TUNASYNC_WORKING_DIR']) / 'iso'
work.mkdir(parents=True, exist_ok=True)
user_agent = os.environ.get('TUNASYNC_TSUMUGU_USERAGENT', 'tsumugu')
max_delete = int(os.environ.get('TUNASYNC_PROXMOX_ISO_MAXDELETE', '100'))

class LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'a':
            return
        for k, v in attrs:
            if k.lower() == 'href' and v:
                self.hrefs.append(v)

req = urllib.request.Request(base, headers={'User-Agent': user_agent})
with urllib.request.urlopen(req, timeout=60) as resp:
    html = resp.read().decode('utf-8', 'replace')

parser = LinkParser()
parser.feed(html)
files = []
seen = set()
for href in parser.hrefs:
    url = urllib.parse.urljoin(base, href)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https') or parsed.netloc != allowed_netloc:
        continue
    if not parsed.path.startswith('/iso/'):
        continue
    name = urllib.parse.unquote(Path(parsed.path).name)
    if not name or name in ('.', '..') or name.endswith('/'):
        continue
    # The page itself is not part of the downloadable ISO artifact set. Keeping
    # it would make us mirror presentation HTML rather than repository content.
    if name == 'index.html':
        continue
    # Keep filenames intentionally conservative. If Proxmox ever introduces
    # names outside this set, review the page before broadening the regex.
    if not re.match(r'^[A-Za-z0-9._+~:-]+$', name):
        print(f'skip suspicious iso link: {name}', file=sys.stderr)
        continue
    if name not in seen:
        seen.add(name)
        files.append((name, urllib.parse.urljoin(base, urllib.parse.quote(name))))

if not files:
    raise SystemExit('no ISO files found on Proxmox ISO page')

print(f'proxmox iso: discovered {len(files)} files', flush=True)
remote_names = {name for name, _ in files}
errors = []
for name, url in files:
    target = work / name
    print(f'proxmox iso: checking {name}', flush=True)
    size = -1
    mtime = None
    try:
        head_req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': user_agent})
        with urllib.request.urlopen(head_req, timeout=30) as resp:
            size = int(resp.headers.get('Content-Length', '-1'))
            lm = resp.headers.get('Last-Modified')
            if lm:
                dt = email.utils.parsedate_to_datetime(lm)
                if dt:
                    mtime = dt.timestamp()
    except Exception as e:
        # Some servers / CDNs reject HEAD with 4xx/405 even when GET works.
        # Try a Range:bytes=0-0 GET so we still get Content-Range / Last-Modified
        # and can decide whether the local file is up to date.
        try:
            range_req = urllib.request.Request(
                url,
                headers={'User-Agent': user_agent, 'Range': 'bytes=0-0'},
            )
            with urllib.request.urlopen(range_req, timeout=30) as resp:
                cr = resp.headers.get('Content-Range', '')
                if cr.startswith('bytes ') and '/' in cr:
                    try:
                        size = int(cr.rsplit('/', 1)[1])
                    except ValueError:
                        pass
                if size < 0:
                    cl = resp.headers.get('Content-Length')
                    if cl is not None:
                        try:
                            size = int(cl)
                        except ValueError:
                            pass
                lm = resp.headers.get('Last-Modified')
                if lm:
                    dt = email.utils.parsedate_to_datetime(lm)
                    if dt:
                        mtime = dt.timestamp()
        except Exception as e2:
            # A transient HEAD/GET failure for a file we already have should
            # not delete or re-download the local file. A missing local file
            # plus failure is recorded as an error so the job exits non-zero.
            if target.exists():
                print(f'proxmox iso: HEAD/GET failed for existing {name}: {e}; '
                      f'keeping local file', flush=True)
                continue
            print(f'proxmox iso: HEAD/GET failed for missing {name}: '
                  f'{e!r} / {e2!r}', file=sys.stderr, flush=True)
            errors.append(f'{name}: HEAD {e!r} / GET {e2!r}')
            continue
    if target.exists() and size >= 0 and target.stat().st_size == size:
        print(f'proxmox iso: skipping {name}', flush=True)
        if mtime:
            os.utime(target, (mtime, mtime))
        continue
    tmp = work / ('.tmp.' + name)
    print(f'proxmox iso: downloading {name} ({size} bytes)', flush=True)
    try:
        get_req = urllib.request.Request(url, headers={'User-Agent': user_agent})
        with urllib.request.urlopen(get_req, timeout=60) as resp, tmp.open('wb') as out:
            shutil.copyfileobj(resp, out, length=1024 * 1024)
        if size >= 0 and tmp.stat().st_size != size:
            raise RuntimeError(f'size mismatch: got {tmp.stat().st_size}, expected {size}')
        tmp.replace(target)
        if mtime:
            os.utime(target, (mtime, mtime))
    except Exception as e:
        tmp.unlink(missing_ok=True)
        print(f'proxmox iso: download failed for {name}: {e}', file=sys.stderr, flush=True)
        errors.append(f'{name}: GET {e}')
        continue

if errors:
    raise SystemExit('proxmox iso: completed with errors: ' + '; '.join(errors))

# Delete only stale regular files directly under /iso/. This cannot affect
# /debian/ or /images/ because this stage never traverses outside work.
stale = [p for p in work.iterdir() if p.is_file() and not p.name.startswith('.tmp.') and p.name not in remote_names]
if len(stale) > max_delete:
    raise SystemExit(f'proxmox iso: refusing to delete {len(stale)} stale files > max {max_delete}')
for p in stale:
    print(f'proxmox iso: deleting stale {p.name}', flush=True)
    p.unlink()
print('proxmox iso: finished', flush=True)
PY
