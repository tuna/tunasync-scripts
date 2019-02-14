#!/usr/bin/env python3
import hashlib
import logging
import os
import re
import requests

from pyquery import PyQuery as pq
from datetime import datetime, timedelta
from pathlib import Path

from urllib3.util.retry import Retry

UPSTREAM_URL = os.getenv("TUNASYNC_UPSTREAM_URL", 'https://nixos.org/releases/nix/')
MIRROR_BASE_URL = os.getenv("MIRROR_BASE_URL", 'https://mirrors.tuna.tsinghua.edu.cn/nix')
WORKING_DIR = os.getenv("TUNASYNC_WORKING_DIR", 'working')
CLONE_SINCE = datetime(2018, 6, 1)
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

def clone_releases():
    working_dir.mkdir(parents=True, exist_ok=True)

    release_base_url = UPSTREAM_URL
    release_links = get_links(f'{release_base_url}/')

    for release_target, release_updated in release_links:
        ver = release_target.rstrip('/')

        if not ver.startswith('nix-'):
            continue

        ver_path = working_dir / ver

        if datetime.strptime(release_updated,'%Y-%m-%d %H:%M') < CLONE_SINCE:
            continue

        logging.info(f'{ver}')

        try:
            with (ver_path / '.latest-fetched').open() as f:
                stamp = f.read()
        except (IOError, OSError):
            stamp = 'not available'

        has_hash_fail = False
        has_updates = stamp != release_updated

        if has_updates:
            ver_path.mkdir(exist_ok=True)

            version_links = get_links(f'{release_base_url}/{ver}/')

            download_links = [
                file_name
                for file_name, _file_updated in version_links
                if not file_name.startswith(f'install') \
                    and not file_name.endswith('/')
            ]

            sha256_links = [
                file_name
                for file_name in download_links
                if file_name.endswith('.sha256')
            ]

            sha256_avail = { }

            if sha256_links:
                logging.info(f'  - Downloading hashes')

                for file_name in sha256_links:
                    logging.info(f'    - {file_name}')
                    checked_file = file_name[: -len('.sha256')]
                    res = http_get(f'{release_base_url}/{ver}/{file_name}')
                    res.raise_for_status()
                    sha256 = res.text
                    if len(sha256) != 64:
                        logging.warn('      - Invalid hash')
                    sha256_avail[checked_file] = sha256

            logging.info(f'  - Downloading files')

            existing = set()

            for file_name in download_links:
                if file_name in sha256_avail \
                    and (ver_path / file_name).is_file() \
                    and sha256_avail[file_name] == file_sha256(ver_path / file_name):
                        logging.info(f'    - {file_name} (existing)')
                        existing.add(file_name)
                else:
                    logging.info(f'    - {file_name}')
                    download(
                        f'{release_base_url}/{ver}/{file_name}',
                        ver_path / file_name)

            if sha256_avail:
                logging.info('  - Verifying files')

                for file_name, sha256 in sha256_avail.items():
                    if not (ver_path / file_name).exists() \
                        or file_name in existing:
                        continue

                    hash = file_sha256(ver_path / file_name)
                    if hash == sha256:
                        logging.info(f'    - [  OK  ] {file_name}')
                    else:
                        has_hash_fail = True
                        logging.info(f'    - [ FAIL ] {file_name}')
                        logging.error(f'      Wrong hash for {file_name}')
                        logging.error(f'      - expected {sha256}')
                        logging.error(f'      - got      {hash}')

        installer_res = http_get(f'{release_base_url}/{ver}/install')

        if installer_res == 404:
            logging.info('  - Installer not found')
        else:
            installer_res.raise_for_status()

            logging.info('  - Writing installer')

            patched_text = installer_res.text.replace(UPSTREAM_URL, MIRROR_BASE_URL)
            atomic_write_file(ver_path / 'install', patched_text)
            atomic_write_file(ver_path / 'install.sha256', file_sha256(ver_path / 'install'))

        if has_updates:
            if has_hash_fail:
                logging.warn(f'  - Found bad files. Not marking update as finished')
            else:
                logging.info(f'  - {ver} updated to {release_updated}')
                atomic_write_file(ver_path / '.latest-fetched', release_updated)

    for latest_link, _latest_updated in get_links(f'{release_base_url}/latest/'):
        res = re.match('(nix-.+?)-.*', latest_link)
        if res is None:
            continue

        ver = res[1]

        logging.info(f'latest -> {ver}')
        (working_dir / '.latest.tmp').symlink_to(ver)
        (working_dir / '.latest.tmp').rename(working_dir / 'latest')

        break


if __name__ == '__main__':
    clone_releases()
