#!/usr/bin/env python3
import hashlib
import logging
import lzma
import os
import re
import sys
import requests
import subprocess

from pyquery import PyQuery as pq
from datetime import datetime, timedelta
from pathlib import Path

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

STORE_DIR = 'store'
RELEASES_DIR = 'releases'
CLONE_SINCE = datetime(2018, 12, 1)
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

def http_head(*args, **kwargs):
    return session.head(*args, timeout=TIMEOUT, **kwargs)

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

def get_links(url):
    r = http_get(url)
    r.raise_for_status()

    node = pq(r.content)

    links = []
    for row in node('tr'):
        td = pq(row)('td')
        if len(td) != 5:
            continue

        link_target = td[1].find('a').get('href')
        if link_target.startswith('/'):
            # Link to parent directory
            continue

        last_updated = td[2].text.strip()

        links.append((link_target, last_updated))

    return links

def clone_channels():
    logging.info(f'- Fetching channels')

    channels_to_update = []

    working_dir.mkdir(parents=True, exist_ok=True)

    for channel, chan_updated in get_links(f'{UPSTREAM_URL}/'):
        chan_path = working_dir / channel

        # Old channels, little value in cloning and format changes
        if datetime.strptime(chan_updated, '%Y-%m-%d %H:%M') < CLONE_SINCE:
            continue

        chan_redirect_res = http_head(f'{UPSTREAM_URL}/{channel}', allow_redirects=False)
        chan_redirect_res.raise_for_status()

        chan_location = chan_redirect_res.headers['Location']

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

def update_channels(channels):
    logging.info(f'- Updating binary cache')

    has_cache_info = False

    for channel in channels:
        logging.info(f'  - {channel}')

        chan_path_update = working_dir / f'.{channel}.update'

        upstream_binary_cache = (chan_path_update / '.original-binary-cache-url').read_text()

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

        # xargs can splits up the argument lists and invokes nix copy multiple
        # times to avoid E2BIG (Argument list too long)
        nix_process = subprocess.Popen(
            [ 'xargs', 'nix', 'copy',
                '--from', upstream_binary_cache,
                '--to', nix_store_dest,
                '--verbose'
            ],
            universal_newlines=True,
            stdin=subprocess.PIPE
        )

        for path in paths:
            nix_process.stdin.write(path.decode() + '\n')

        retcode = nix_process.wait()

        if retcode == 0:
            chan_path_update.rename(working_dir / channel)
            logging.info(f'    - Done')
        else:
            global failure
            failure = True

            logging.info(f'    - nix copy failed')

if __name__ == '__main__':
    channels = clone_channels()
    update_channels(channels)
    if failure:
        sys.exit(1)
