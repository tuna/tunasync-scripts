#!/usr/bin/env python3
import email.utils
import hashlib
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
# conservative filenames, and validate redirect targets against the same
# allowlist, so a layout change or unexpected external link cannot cause
# arbitrary downloads.
#
# Only the top-level /iso/ listing is mirrored; links pointing into
# subdirectories of /iso/ are skipped. The upstream page is flat today, but
# unlike the old recursive `lftp mirror` this scraper would need to be
# extended if Proxmox ever introduces subdirectories.
#
# Completeness model:
#   * remote_names is derived from the official /iso/ page's same-host links.
#   * each remote file is probed (HEAD, or a ranged GET when HEAD is
#     rejected) to obtain Content-Length and Last-Modified.
#   * an existing local file is kept only when every available signal matches:
#     size when Content-Length was sent, and Last-Modified compared against
#     the local mtime when it was sent (matching lftp --only-newer/tsumugu
#     semantics, so a same-size replacement such as a re-signed .asc or a
#     re-spun ISO is re-fetched). With neither signal the file is
#     re-downloaded.
#   * changed/missing files are downloaded to .tmp.<name> first, then
#     atomically renamed into place; the local mtime is set to the upstream
#     Last-Modified.
#   * downloaded payloads are verified against their published .sha256 files
#     (.sha256 files are fetched first exactly for this). A mismatch removes
#     both sides of the pair so the next run re-fetches a consistent set.
#   * stale local files under /iso/ are removed only after all remote links
#     have been processed, and only if the count is <=
#     TUNASYNC_PROXMOX_ISO_MAXDELETE.
socket.setdefaulttimeout(60)
base = os.environ.get('TUNASYNC_UPSTREAM_URL', 'http://download.proxmox.com/').rstrip('/') + '/iso/'
# The same-host allowlist and path prefix follow the configured upstream
# instead of hardcoded constants, so a mirror/proxy upstream still works.
allowed_netloc = urllib.parse.urlparse(base).netloc
base_path = urllib.parse.urlparse(base).path
try:
    work = Path(os.environ['TUNASYNC_WORKING_DIR']) / 'iso'
except KeyError:
    raise SystemExit('proxmox iso: TUNASYNC_WORKING_DIR is not set; tunasync sets it '
                     'for every job — set it to the mirror root when running manually')
work.mkdir(parents=True, exist_ok=True)
user_agent = os.environ.get('TUNASYNC_TSUMUGU_USERAGENT', 'tsumugu')
max_delete = int(os.environ.get('TUNASYNC_PROXMOX_ISO_MAXDELETE', '100'))

# A killed run leaves partial .tmp.* downloads behind. They are never resumed
# (downloads restart from scratch and rename atomically), so remove them
# before doing anything else; otherwise a partial file whose remote name
# disappears would stay on disk (and get served) forever.
for leftover in work.glob('.tmp.*'):
    if leftover.is_file():
        print(f'proxmox iso: removing leftover {leftover.name}', flush=True)
        leftover.unlink()


def open_allowed(req, timeout):
    """urlopen() that refuses redirects leaving the allowed origin/path.

    urllib follows redirects silently; an artifact link redirecting to
    another host, a non-http(s) scheme, or a path outside base_path must not
    be fetched — that would bypass the allowlist applied during link
    discovery.
    """
    resp = urllib.request.urlopen(req, timeout=timeout)
    final = urllib.parse.urlparse(resp.geturl())
    if (final.scheme not in ('http', 'https') or final.netloc != allowed_netloc
            or not final.path.startswith(base_path)):
        resp.close()
        raise ValueError(f'redirect outside allowed origin/path: {resp.geturl()}')
    return resp


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
with open_allowed(req, timeout=60) as resp:
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
    if not parsed.path.startswith(base_path):
        continue
    # Directory/navigation links end in '/'; check the raw path because
    # Path().name would strip the slash and turn '/iso/' into 'iso'.
    if parsed.path.endswith('/'):
        continue
    # Only the flat top level is mirrored: a path still containing '/' after
    # the base_path prefix lives in a subdirectory (none exist today) and
    # would otherwise be flattened to its basename.
    if '/' in parsed.path[len(base_path):]:
        continue
    name = urllib.parse.unquote(Path(parsed.path).name)
    if not name or name in ('.', '..'):
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


def remote_metadata(url):
    """Return (size, last_modified) for url via HEAD, falling back to GET.

    Some servers/proxies reject HEAD (405/403) while allowing GET. A 1-byte
    range request then yields Content-Range (total size) and Last-Modified
    without downloading the payload; a server ignoring Range answers 200 with
    the full Content-Length, which is equally usable.
    """
    headers = {'User-Agent': user_agent}
    try:
        req = urllib.request.Request(url, method='HEAD', headers=headers)
        with open_allowed(req, timeout=30) as resp:
            return int(resp.headers.get('Content-Length', '-1')), resp.headers.get('Last-Modified')
    except Exception as head_err:
        req = urllib.request.Request(url, headers={**headers, 'Range': 'bytes=0-0'})
        try:
            with open_allowed(req, timeout=30) as resp:
                cr = resp.headers.get('Content-Range', '')
                m = re.match(r'bytes \d+-\d+/(\d+)', cr)
                size = int(m.group(1)) if m else int(resp.headers.get('Content-Length', '-1'))
                print(f'proxmox iso: HEAD rejected ({head_err}); ranged GET gave size={size}', flush=True)
                return size, resp.headers.get('Last-Modified')
        except Exception:
            raise head_err


def up_to_date(target, size, mtime):
    """A local file is fresh only when every signal the server sent matches:
    size when Content-Length was given, and Last-Modified compared against
    the local mtime when given. With neither signal we cannot prove freshness
    and must re-download (previously an absent Content-Length also caused a
    re-download on every run; a matching Last-Modified now suffices).
    """
    if not target.exists():
        return False
    st = target.stat()
    if size >= 0 and st.st_size != size:
        return False
    if mtime is not None:
        return int(st.st_mtime) == int(mtime)
    return size >= 0


def sha256_of(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def expected_sha256(sf, name):
    """Return the hex digest recorded for `name` in .sha256 file `sf`.

    Lines look like "<64 hex chars>  <filename>" (optionally with a '*'
    binary marker). Returns None when no matching entry is found.
    """
    try:
        for line in sf.read_text(errors='replace').splitlines():
            parts = line.split()
            if (len(parts) == 2 and re.fullmatch(r'[0-9a-fA-F]{64}', parts[0])
                    and parts[1].lstrip('*') == name):
                return parts[0].lower()
    except OSError:
        pass
    return None


remote_names = {name for name, _ in files}
errors = []
downloaded = []
# Fetch the tiny .sha256 files first so payloads downloaded afterwards can be
# verified against them immediately.
for name, url in sorted(files, key=lambda f: 0 if f[0].endswith('.sha256') else 1):
    target = work / name
    print(f'proxmox iso: checking {name}', flush=True)
    size = -1
    mtime = None
    try:
        size, lm = remote_metadata(url)
        if lm:
            dt = email.utils.parsedate_to_datetime(lm)
            if dt:
                mtime = dt.timestamp()
    except Exception as e:
        # A transient metadata-probe failure for a file we already have should
        # not delete or re-download the local file. A missing local file plus
        # probe failure is recorded as an error so the job exits non-zero
        # after processing.
        if target.exists():
            print(f'proxmox iso: metadata probe failed for existing {name}: {e}; keeping local file', flush=True)
            continue
        print(f'proxmox iso: metadata probe failed for missing {name}: {e}', file=sys.stderr, flush=True)
        errors.append(f'{name}: probe {e}')
        continue
    if up_to_date(target, size, mtime):
        print(f'proxmox iso: skipping {name}', flush=True)
        continue
    tmp = work / ('.tmp.' + name)
    print(f'proxmox iso: downloading {name} ({size} bytes)', flush=True)
    try:
        get_req = urllib.request.Request(url, headers={'User-Agent': user_agent})
        with open_allowed(get_req, timeout=60) as resp, tmp.open('wb') as out:
            shutil.copyfileobj(resp, out, length=1024 * 1024)
        if size >= 0 and tmp.stat().st_size != size:
            raise RuntimeError(f'size mismatch: got {tmp.stat().st_size}, expected {size}')
        tmp.replace(target)
        if mtime:
            os.utime(target, (mtime, mtime))
        downloaded.append(name)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        print(f'proxmox iso: download failed for {name}: {e}', file=sys.stderr, flush=True)
        errors.append(f'{name}: GET {e}')
        continue

# Verify payloads against their published .sha256 whenever this run fetched a
# fresh copy of either side of the pair. Only pairs still listed upstream are
# considered; stale files are handled by the cleanup below.
to_verify = set()
for n in downloaded:
    to_verify.add(n[:-len('.sha256')] if n.endswith('.sha256') else n)
for name in sorted(to_verify):
    if name not in remote_names or name + '.sha256' not in remote_names:
        continue
    payload = work / name
    sf = work / (name + '.sha256')
    if not payload.is_file() or not sf.is_file():
        continue
    expected = expected_sha256(sf, name)
    if expected is None:
        print(f'proxmox iso: WARNING: no sha256 entry for {name} in {sf.name}; not verified',
              file=sys.stderr, flush=True)
        continue
    print(f'proxmox iso: verifying {name}', flush=True)
    if sha256_of(payload) != expected:
        # Remove both sides so the next run re-fetches a consistent pair
        # instead of failing on the same mismatch forever.
        payload.unlink()
        sf.unlink()
        print(f'proxmox iso: sha256 mismatch for {name}; removed local pair', file=sys.stderr, flush=True)
        errors.append(f'{name}: sha256 mismatch')

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
