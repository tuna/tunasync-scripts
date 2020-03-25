#!/usr/bin/env python3
import hashlib
import logging
import lzma
import minio
import os
import re
import sys
import requests
import subprocess

from pyquery import PyQuery as pq
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

from minio.credentials import Credentials, Static

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

def atomic_write_file(dest, contents):
    dest.parent.mkdir(parents=True, exist_ok=True)
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

credentials = Credentials(provider=Static())
client = minio.Minio('s3.amazonaws.com', credentials=credentials)

def get_url(name):
    response = client.get_object('nix-channels', name)
    return response.headers['x-amz-website-redirect-location']

def clone_images():
    DOWNLOAD_MATCH = r'nixos-\d\d.\d\d/latest-nixos-\w+-\w+-linux.\w+(.sha256)?'

    object_names = [
        x.object_name
        for x in client.list_objects_v2('nix-channels', recursive=True)
        if re.fullmatch(DOWNLOAD_MATCH, x.object_name)
    ]

    channels = defaultdict(lambda: [])

    for name in object_names:
        chan, file = name.split('/', 1)
        channels[chan].append(file)

    for channel, files in channels.items():
        chan_dir = working_dir / channel
        git_rev = http_get(get_url(f'{channel}/git-revision')).text
        git_rev_path = chan_dir / 'git-revision'

        if git_rev_path.exists() and git_rev == git_rev_path.read_text():
            continue

        logging.info(f'- {channel} -> {git_rev}')

        for file in files:
            logging.info(f'  - {file}')
            url = get_url(f'{channel}/{file}')

            try:
                download(url, chan_dir / file)
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    logging.info(f'    - 404, skipped')
                else:
                    raise

        atomic_write_file(git_rev_path, git_rev)

if __name__ == "__main__":
    clone_images()
