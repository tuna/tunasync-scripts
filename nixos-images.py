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

UPSTREAM_URL = os.getenv('TUNASYNC_UPSTREAM_URL', 'https://nixos.org/channels')
WORKING_DIR = os.getenv('TUNASYNC_WORKING_DIR', 'working-images')
CLONE_SINCE = datetime(2018, 12, 1)
TIMEOUT = 60

working_dir = Path(WORKING_DIR)

session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[ 502, 503, 504 ])
retry_adapter = requests.adapters.HTTPAdapter(max_retries=retries)
session.mount('http://', retry_adapter)
session.mount('https://', retry_adapter)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)-8s %(message)s'
)

def http_head(*args, **kwargs):
    return session.head(*args, timeout=TIMEOUT, **kwargs)

def http_get(*args, **kwargs):
    return session.get(*args, timeout=TIMEOUT, **kwargs)

def file_sha256(dest):
    sha = subprocess.check_output(
        [ 'sha256sum', str(dest) ],
        universal_newlines=True
    )
    return sha.split(' ')[0]

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
                    for chunk in res.iter_content(chunk_size=64 * 1024 * 1024):
                        if chunk:
                            f.write(chunk)
                actual_size = download_dest.stat().st_size
                if 'Content-Length' in res.headers:
                    expected_size = int(res.headers['Content-Length'])
                    if actual_size != expected_size:
                        raise WrongSize(expected=expected_size, actual=actual_size)

                break
            except (requests.exceptions.ConnectionError, WrongSize) as e:
                logging.warn(e)
                next_retry = retry.increment(
                    method='GET',
                    url=url,
                    error=e
                )
                if next_retry is None:
                    raise e
                else:
                    retry = next_retry
                    logging.warn(f'Retrying download: {retry}')

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

def get_channel(chan_location):
    release_res = http_get(chan_location)
    release_res.raise_for_status()

    node = pq(release_res.text)

    tagline = node('p').text()

    tagline_res = re.match(r'^Released on (.+) from', tagline)

    assert tagline_res is not None

    released_time = tagline_res[1]

    files = []

    for row in node('tr'):
        td = pq(row)('td')
        if len(td) != 3:
            continue
        file_name, file_size, file_hash = (pq(x).text() for x in td)
        files.append((file_name, file_size, file_hash))

    return {
        'released_time': released_time,
        'files': files
    }

def clone_images():
    for channel, chan_updated in get_links(f'{UPSTREAM_URL}/'):
        if not channel.startswith('nixos-') \
            or channel.endswith('-small') \
            or channel == 'nixos-unstable':
            continue

        if datetime.strptime(chan_updated, '%Y-%m-%d %H:%M') < CLONE_SINCE:
            continue

        chan_path = working_dir / channel
        chan_path.mkdir(parents=True, exist_ok=True)

        res = http_head(f'{UPSTREAM_URL}/{channel}', allow_redirects=False)
        res.raise_for_status()

        chan_location = res.headers['Location']

        try:
            last_url = (chan_path / '.last-url').read_text()
        except (IOError, OSError):
            last_url = 'not available'

        if chan_location == last_url:
            continue

        chan_location_base = chan_location.split('/')[-1]

        logging.info(f'- {channel} -> {chan_location_base}')

        chan_info = get_channel(chan_location)

        atomic_write_file(chan_path / '.released-time', chan_info['released_time'])

        has_hash_fail = False

        keep_files = { '.last-url', '.released-time' }

        logging.info(f'  - Downloading new files')

        image_files = [
            (file_name, file_hash)
            for file_name, _file_size, file_hash in chan_info['files']
            if file_name.endswith('.iso') or file_name.endswith('ova')
        ]

        for file_name, file_hash in image_files:
            keep_files.add(file_name)

            if (chan_path / file_name).is_file() \
                and file_hash == file_sha256(chan_path / file_name):
                logging.info(f'    - {file_name} (existing)')
            else:
                logging.info(f'    - {file_name}')
                download(f'{chan_location}/{file_name}', chan_path / file_name)
                actual_hash = file_sha256(chan_path / file_name)
                if file_hash != actual_hash:
                    has_hash_fail = True

                    logging.error(f'      - Incorrect hash')
                    logging.error(f'        actual   {actual_hash}')
                    logging.error(f'        expected {file_sha256}')

        logging.info(f'  - Removing old files')

        for file_path in chan_path.iterdir():
            file_name = file_path.name

            if file_name not in keep_files:
                logging.info(f'    - {file_name}')
                file_path.unlink()

        logging.info(f'  - Writing SHA256SUMS')

        with (chan_path / 'SHA256SUMS').open('w') as f:
            for file_name, file_hash in image_files:
                f.write(f'{file_hash} *{file_name}\n')

        if has_hash_fail:
            logging.warn(f'  - Found bad files. Not marking update as finished')
        else:
            logging.info(f'  - Update finished')
            atomic_write_file(chan_path / '.last-url', chan_location)

if __name__ == "__main__":
    clone_images()
