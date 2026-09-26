#!/usr/bin/env python3
import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

UA = os.environ.get('PHP_SYNC_UA', 'tunasync php-sync')
API_URL = 'https://www.php.net/releases/index.php'
DIST_URL = 'https://www.php.net/distributions/'
TIMEOUT = 120
RETRIES = 3
# Patch releases to fetch per supported line; without max the API returns
# only the latest patch release of the line.
MAX_PER_LINE = 10

WORKING_DIR = Path(os.environ['TUNASYNC_WORKING_DIR'])

# php.net is behind BunnyCDN; from some networks its IPv4 is unreachable or
# slow while IPv6 works fine. Set PHP_SYNC_PREFER_IPV6=1 to try IPv6
# addresses first (IPv4 remains as fallback). Off by default: on networks
# where IPv6 packets are silently dropped, every connection would otherwise
# wait the full TIMEOUT before falling back to IPv4.
_getaddrinfo = socket.getaddrinfo


def _ipv6_first(*args, **kwargs):
    res = _getaddrinfo(*args, **kwargs)
    res.sort(key=lambda r: r[0] != socket.AF_INET6)
    return res


if os.environ.get('PHP_SYNC_PREFER_IPV6'):
    socket.getaddrinfo = _ipv6_first


def get_json(url):
    # BunnyCDN caches the releases API for up to 30 days and keys its cache
    # on the full query string, so a unique parameter busts the edge cache
    # and new releases are seen immediately.
    url += ('&' if '?' in url else '?') + f'_={int(time.time())}'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def remote_filelist():
    files = {}
    top = get_json(f'{API_URL}?json&max=1')
    lines = set()
    for rel in top.values():
        lines.update(rel.get('supported_versions') or [])
    for line in sorted(lines):
        # With max, the response is a map keyed by full version.
        releases = get_json(
            f'{API_URL}?json&version={line}&max={MAX_PER_LINE}')
        for rel in releases.values():
            for src in rel.get('source', []):
                if 'sha256' not in src:
                    continue
                filename = src.get('filename', '')
                # Only accept plain basenames; anything else could escape
                # WORKING_DIR when used to build local paths.
                if (not filename or filename in ('.', '..')
                        or Path(filename).name != filename):
                    print(f'WARN: ignoring suspicious filename {filename!r}',
                          flush=True)
                    continue
                files[filename] = src['sha256']
    return files


def set_mtime(path, last_modified):
    # Keep the upstream Last-Modified time as mtime, so listings show when a
    # file was released rather than when it was synced.
    if not last_modified:
        return
    try:
        ts = parsedate_to_datetime(last_modified).timestamp()
        os.utime(path, (ts, ts))
    except (TypeError, ValueError):
        pass


def download(filename, sha256):
    dst = WORKING_DIR / filename
    tmp = dst.with_name(dst.name + '.tmp')
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(DIST_URL + filename,
                                         headers={'User-Agent': UA})
            h = hashlib.sha256()
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r, \
                    open(tmp, 'wb') as f:
                last_modified = r.headers.get('Last-Modified')
                while chunk := r.read(1024 ** 2):
                    f.write(chunk)
                    h.update(chunk)
            if h.hexdigest() != sha256:
                raise Exception(f'sha256 mismatch: got {h.hexdigest()}')
            os.rename(tmp, dst)
            set_mtime(dst, last_modified)
            return True
        except Exception as e:
            print(f'failed {filename} (attempt {attempt}/{RETRIES}): {e}',
                  flush=True)
            tmp.unlink(missing_ok=True)
    return False


def download_asc(filename):
    # .asc signatures are not in the JSON API; they are optional, so failures
    # (including 404) never affect the run result.
    dst = WORKING_DIR / (filename + '.asc')
    if dst.is_file() and dst.stat().st_size > 0:
        return
    tmp = dst.with_name(dst.name + '.tmp')
    try:
        req = urllib.request.Request(DIST_URL + filename + '.asc',
                                     headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r, \
                open(tmp, 'wb') as f:
            last_modified = r.headers.get('Last-Modified')
            f.write(r.read())
        os.rename(tmp, dst)
        set_mtime(dst, last_modified)
        print(f'downloaded {filename}.asc', flush=True)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f'WARN: {filename}.asc: {e}', flush=True)
        tmp.unlink(missing_ok=True)
    except Exception as e:
        print(f'WARN: {filename}.asc: {e}', flush=True)
        tmp.unlink(missing_ok=True)


def local_ok(dst, sha256):
    # A non-empty local file is only trusted if its hash matches what the
    # API published; truncated/corrupted leftovers get re-downloaded.
    if not dst.is_file() or dst.stat().st_size == 0:
        return False
    h = hashlib.sha256()
    with open(dst, 'rb') as f:
        while chunk := f.read(1024 ** 2):
            h.update(chunk)
    if h.hexdigest() != sha256:
        print(f'WARN: {dst.name} exists but sha256 mismatch, re-downloading',
              flush=True)
        return False
    return True


def main():
    files = remote_filelist()
    if not files:
        # An empty list means the API response shape changed; fail loudly
        # instead of reporting success while the mirror goes stale.
        sys.exit('ERROR: no files from the releases API')
    downloaded, skipped, failed = 0, 0, 0
    for filename, sha256 in sorted(files.items()):
        dst = WORKING_DIR / filename
        if local_ok(dst, sha256):
            print(f'skipping {filename}', flush=True)
            skipped += 1
        else:
            print(f'downloading {filename}', flush=True)
            if download(filename, sha256):
                downloaded += 1
            else:
                failed += 1
                if dst.is_file():
                    # A failed repair must not leave a known-corrupt file
                    # served; remove it so the next run starts clean.
                    dst.unlink()
                    print(f'ERROR: giving up on {filename}, removed the '
                          f'corrupt local file', flush=True)
                else:
                    print(f'ERROR: giving up on {filename}', flush=True)
        if dst.is_file():
            download_asc(filename)
    print(f'downloaded: {downloaded}, skipped: {skipped}, failed: {failed}',
          flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
