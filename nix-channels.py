#!/usr/bin/env python3
import hashlib
import json
import logging
import lzma
import minio
import os
import pytz
import re
import requests
import subprocess
import sys

from pyquery import PyQuery as pq
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from urllib3.util.retry import Retry

### Config

if len(sys.argv) > 1 and sys.argv[1] == '--ustc':
    # Mode for https://github.com/ustclug/ustcmirror-images
    UPSTREAM_URL = os.getenv("NIX_MIRROR_UPSTREAM", 'https://nixos.org/channels')
    MIRROR_BASE_URL = os.getenv("NIX_MIRROR_BASE_URL", 'https://mirrors.ustc.edu.cn/nix-channels')
    WORKING_DIR = os.getenv("TO", 'working-channels')
else:
    UPSTREAM_URL = os.getenv("TUNASYNC_UPSTREAM_URL", 'https://nixos.org/channels')
    MIRROR_BASE_URL = os.getenv("MIRROR_BASE_URL", 'https://mirrors.tuna.tsinghua.edu.cn/nix-channels')
    WORKING_DIR = os.getenv("TUNASYNC_WORKING_DIR", 'working-channels')

PATH_BATCH = int(os.getenv('NIX_MIRROR_PATH_BATCH', 8192))
THREADS = int(os.getenv('NIX_MIRROR_THREADS', 10))
DELETE_OLD = os.getenv('NIX_MIRROR_DELETE_OLD', '1') == '1'
RETAIN_DAYS = float(os.getenv('NIX_MIRROR_RETAIN_DAYS', 30))

STORE_DIR = 'store'
RELEASES_DIR = 'releases'

# Channels that have not updated since migration to Netlify [1] are assumed to
# be too old and defunct.
#
# [1]: https://discourse.nixos.org/t/announcement-moving-nixos-org-to-netlify/6212
CLONE_SINCE = datetime(2020, 3, 6, tzinfo=pytz.utc)
TIMEOUT = 60

working_dir = Path(WORKING_DIR)

# `nix copy` uses a cache database
# TODO Should we expose this directory?
os.environ['XDG_CACHE_HOME'] = str((working_dir / '.cache').resolve())

nix_store_dest = f'file://{(working_dir / STORE_DIR).resolve()}'

binary_cache_url = f'{MIRROR_BASE_URL}/{STORE_DIR}'

session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[ 502, 503, 504 ])
retry_adapter = requests.adapters.HTTPAdapter(max_retries=retries)
session.mount('http://', retry_adapter)
session.mount('https://', retry_adapter)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)-8s %(message)s'
)

# Set this to True if some sub-process failed
# Don't forget 'global failure'
failure = False

def http_get(*args, **kwargs):
    return session.get(*args, timeout=TIMEOUT, **kwargs)

# Adapted from anaconda.py

def file_sha256(dest):
    m = hashlib.sha256()
    with dest.open('rb') as f:
        while True:
            buf = f.read(1*1024*1024)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest()

def atomic_write_file(dest, contents):
    tmp_dest = dest.parent / f'.{dest.name}.tmp'
    with tmp_dest.open('w') as f:
        f.write(contents)
    tmp_dest.rename(dest)

class WrongSize(RuntimeError):
    def __init__(self, expected, actual):
        super().__init__(f'Wrong file size: expected {expected}, actual {actual}')
        self.actual = actual
        self.expected = expected

def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    download_dest = dest.parent / f'.{dest.name}.tmp'

    retry = retries

    while True:
        with http_get(url, stream=True) as res:
            res.raise_for_status()
            try:
                with download_dest.open('wb') as f:
                    for chunk in res.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                actual_size = download_dest.stat().st_size
                if 'Content-Length' in res.headers:
                    expected_size = int(res.headers['Content-Length'])
                    if actual_size != expected_size:
                        raise WrongSize(expected=expected_size, actual=actual_size)

                break
            except (requests.exceptions.ConnectionError, WrongSize) as e:
                logging.warning(e)
                next_retry = retry.increment(
                    method='GET',
                    url=url,
                    error=e
                )
                if next_retry is None:
                    global failure
                    failure = True
                    raise e
                else:
                    retry = next_retry
                    logging.warning(f'Retrying download: {retry}')

    download_dest.rename(dest)

client = minio.Minio('s3.amazonaws.com')

def get_channels():
    return [
        (x.object_name, x.last_modified)
        for x in client.list_objects_v2('nix-channels')
        if re.fullmatch(r'(nixos|nixpkgs)-.+[^/]', x.object_name)
    ]

def clone_channels():
    logging.info(f'- Fetching channels')

    channels_to_update = []

    working_dir.mkdir(parents=True, exist_ok=True)

    for channel, chan_updated in get_channels():
        chan_path = working_dir / channel

        # Old channels, little value in cloning and format changes
        if chan_updated < CLONE_SINCE:
            continue

        chan_obj = client.get_object('nix-channels', channel)
        chan_location = chan_obj.headers['x-amz-website-redirect-location']

        chan_release = chan_location.split('/')[-1]

        release_target = f'{RELEASES_DIR}/{channel}@{chan_release}'

        release_path = working_dir / release_target

        if chan_path.is_symlink() \
            and os.readlink(str(chan_path)) == release_target:
            continue

        chan_path_update = working_dir / f'.{channel}.update'

        if chan_path_update.is_symlink() \
            and os.readlink(str(chan_path_update)) == release_target:
            channels_to_update.append(channel)
            logging.info(f'  - {channel} ready to update to {chan_release}')
            continue

        logging.info(f'  - {channel} -> {chan_release}')

        release_res = http_get(chan_location)
        if release_res.status_code == 404:
            logging.warning(f'    - Not found')
            continue

        release_res.raise_for_status()
        node = pq(release_res.text)

        tagline = node('p').text()

        tagline_res = re.match(r'^Released on (.+) from', tagline)

        if tagline_res is None:
            logging.warning(f'    - Invalid tagline: {tagline}')
            continue

        released_time = tagline_res[1]

        release_path.mkdir(parents=True, exist_ok=True)

        with (release_path / '.released-time').open('w') as f:
            f.write(released_time)

        logging.info(f'    - Downloading files')

        has_hash_fail = False

        for row in node('tr'):
            td = pq(row)('td')
            if len(td) != 3:
                continue
            file_name, _file_size, file_hash = (pq(x).text() for x in td)

            if file_name.endswith('.ova') or file_name.endswith('.iso'):
                # Skip images
                pass
            elif (release_path / file_name).exists() \
                and file_sha256(release_path / file_name) == file_hash:
                logging.info(f'      - {file_name} (existing)')
            else:
                if file_name == 'binary-cache-url':
                    logging.info(f'      - binary-cache-url (redirected)')
                    dest = '.original-binary-cache-url'
                else:
                    logging.info(f'      - {file_name}')
                    dest = file_name

                download(f'{chan_location}/{file_name}', release_path / dest)
                if file_sha256(release_path / dest) != file_hash:
                    global failure
                    failure = True

                    has_hash_fail = True
                    logging.error(f'        Wrong hash!')
                    logging.error(f'        - expected {file_hash}')
                    logging.error(f'        - got      {hash}')

        logging.info('    - Writing binary-cache-url')
        (release_path / 'binary-cache-url').write_text(binary_cache_url)

        if has_hash_fail:
            logging.warning('    - Found bad files. Not updating symlink.')
        else:
            channels_to_update.append(channel)
            if chan_path_update.exists():
                chan_path_update.unlink()
            chan_path_update.symlink_to(release_target)

            logging.info(f'    - Symlink updated')

    return channels_to_update

def hash_part(path):
    return path.split('/')[-1].split('-', 1)[0]

def update_channels(channels):
    logging.info(f'- Updating binary cache')

    has_cache_info = False

    for channel in channels:
        logging.info(f'  - {channel}')

        chan_path = working_dir / channel
        chan_path_update = working_dir / f'.{channel}.update'

        upstream_binary_cache = (chan_path_update / '.original-binary-cache-url').read_text()
        upstream_binary_cache = upstream_binary_cache.rstrip('/')

        # All the channels should have https://cache.nixos.org as binary cache
        # URL. We download nix-cache-info here (once per sync) to avoid
        # hard-coding it, and in case it changes.
        if not has_cache_info:
            info_file = 'nix-cache-info'
            logging.info(f'    - Downloading {info_file}')
            download(
                f'{upstream_binary_cache}/{info_file}',
                working_dir / STORE_DIR / info_file
            )
            has_cache_info = True

        with lzma.open(str(chan_path_update / 'store-paths.xz')) as f:
            paths = [ path.rstrip() for path in f ]

        logging.info(f'    - {len(paths)} paths listed')

        todo = {}
        channel_failure = False

        # Batch paths to avoid E2BIG

        for i in range(0, len(paths), PATH_BATCH):
            batch = paths[i : i + PATH_BATCH]
            process = subprocess.run(
                [
                    'nix', 'path-info',
                    '--store', upstream_binary_cache,
                    '--recursive', '--json'
                ] + batch,
                stdout=subprocess.PIPE
            )
            if process.returncode != 0:
                channel_failure = True
                logging.info(f'    - Error status: {process.returncode}')
                break
        else:
            infos = json.loads(process.stdout)
            for info in infos:
                ha = hash_part(info['path'])
                todo[ha] = (info['url'], f'{ha}.narinfo')

            logging.info(f'    - {len(todo)} paths to download')

            digits = len(str(len(todo)))

            def try_mirror(index, paths):
                index += 1
                prefix = f'[{str(index).rjust(digits)}/{len(todo)}]'
                try:
                    for path in paths:
                        url = f'{upstream_binary_cache}/{path}'
                        dest = working_dir / STORE_DIR / path
                        if dest.exists(): continue
                        download(url, dest)
                        logging.info(f'    - {prefix} {path}')
                    return True
                except (requests.exceptions.ConnectionError, WrongSize):
                    return False

            with ThreadPoolExecutor(max_workers=THREADS) as executor:
                results = executor.map(
                    lambda job: try_mirror(*job),
                    enumerate(todo.values())
                )
                if not all(results):
                    channel_failure = True

        if channel_failure:
            logging.info(f'    - Finished with errors, not updating symlink')
        else:
            chan_path_update.rename(chan_path)
            logging.info(f'    - Finished with success, symlink updated')

def parse_narinfo(narinfo):
    res = {}
    for line in narinfo.splitlines():
        key, value = line.split(': ', 1)
        res[key] = value
    return res

def garbage_collect():
    logging.info(f'- Collecting garbage')

    time_threshold = datetime.now() - timedelta(days=RETAIN_DAYS)

    last_updated = {}
    latest = {}
    alive = set()

    for release in (working_dir / RELEASES_DIR).iterdir():
        channel = release.name.split('@')[0]
        date_str = (release / '.released-time').read_text()
        released_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')

        if released_date >= time_threshold:
            alive.add(release)

        if channel not in last_updated \
            or last_updated[channel] < released_date:
            last_updated[channel] = released_date
            latest[channel] = release

    alive.update(latest.values())

    logging.info(f'  - {len(alive)} releases alive')

    closure = set()

    for release in alive:
        with lzma.open(str(release / 'store-paths.xz')) as f:
            paths = [ path.rstrip() for path in f ]

        for i in range(0, len(paths), PATH_BATCH):
            batch = paths[i : i + PATH_BATCH]

            process = subprocess.run(
                [
                    'nix', 'path-info',
                    '--store', nix_store_dest,
                    '--recursive'
                ] + batch,
                stdout=subprocess.PIPE
            )

            for path in process.stdout.decode().splitlines():
                closure.add(hash_part(path))

    logging.info(f'  - {len(closure)} paths in closure')

    deleted = 0

    for path in (working_dir / STORE_DIR).iterdir():
        if not path.name.endswith('.narinfo'):
            continue

        hash = path.name.split('.narinfo', 1)[0]
        if hash in closure:
            continue

        deleted += 1

        if DELETE_OLD:
            narinfo = parse_narinfo(path.read_text())
            path.unlink(missing_ok=True)
            (working_dir / STORE_DIR / narinfo['URL']).unlink(missing_ok=True)

    if DELETE_OLD:
        logging.info(f'  - {deleted} paths deleted')
    else:
        logging.info(f'  - {deleted} paths now unreachable')

if __name__ == '__main__':
    channels = clone_channels()
    update_channels(channels)
    garbage_collect()
    if failure:
        sys.exit(1)
