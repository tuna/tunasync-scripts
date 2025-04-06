#!/usr/bin/env python3
import hashlib
import os
import subprocess as sp
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Set
import requests

DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', '1800'))
BASE_PATH = os.getenv('TUNASYNC_WORKING_DIR')
BASE_URL = os.getenv('TUNASYNC_UPSTREAM_URL', "https://packages.adoptium.net/ui/native")
FEATURE_VERSIONS = [8, 11, 17, 20, 21]

def download_file(url: str, dst_file: Path)->bool:
    try:
        start = time.time()
        with requests.get(url, stream=True, timeout=(5, 10)) as r:
            r.raise_for_status()
            if 'last-modified' in r.headers:
                remote_ts = parsedate_to_datetime(
                    r.headers['last-modified']).timestamp()
            else: remote_ts = None

            with dst_file.open('wb') as f:
                for chunk in r.iter_content(chunk_size=1024**2):
                    if time.time() - start > DOWNLOAD_TIMEOUT:
                        raise TimeoutError("Download timeout")
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
            if remote_ts is not None:
                os.utime(dst_file, (remote_ts, remote_ts))
        return True
    except BaseException as e:
        print(e, flush=True)
        if dst_file.is_file():
            dst_file.unlink()
    return False

def check_file(dest_filename: Path, pkg_checksum: str, size: int)->bool:
    if dest_filename.stat().st_size != size:
        print(f"Wrong size of {dest_filename}, expected {size}")
        return False
    sha = hashlib.sha256()
    with dest_filename.open("rb") as f:
        for block in iter(lambda: f.read(1024**2), b""):
            sha.update(block)
    if sha.hexdigest() != pkg_checksum:
        print(f"Invalid checksum of {dest_filename}, expected {pkg_checksum}")
        return False
    return True

def download_release(ver: int, jvm_impl: str, alive_files: Set[str]):
    r = requests.get(f"https://api.adoptium.net/v3/assets/latest/{ver}/{jvm_impl}",
            timeout=(5, 10),
            headers={ 'User-Agent': 'tunasync-scripts (+https://github.com/tuna/tunasync-scripts)' })
    r.raise_for_status()
    rel_list = r.json()
    rel_path = Path(BASE_PATH) / str(ver)
    for rel in rel_list:
        binary = rel['binary']
        if binary['image_type'] not in ('jre', 'jdk'): continue
        dst_dir = rel_path / binary['image_type'] / binary['architecture'] / binary['os']
        dst_dir.mkdir(parents=True, exist_ok=True)
        for f in ('package', 'installer'):
            if f not in binary: continue
            meta = binary[f]
            filename, tmpfile = dst_dir / meta['name'], dst_dir / ('.' + meta['name'])
            alive_files.add(str(filename.relative_to(rel_path)))
            if filename.is_file() and filename.stat().st_size == meta['size']:
                print(f"Skiping {filename}")
                continue

            print(f"Downloading {tmpfile}", flush=True)
            for retry in range(3):
                if download_file(meta['link'], tmpfile) and \
                    check_file(tmpfile, meta['checksum'], meta['size']):
                    tmpfile.rename(filename)
                    break
            else:
                print(f"Failed to download {meta['link']}", flush=True)

def delete_old_files(ver: int, alive_files: Set[str]):
    rel_path = Path(BASE_PATH) / str(ver)
    on_disk = set([
        str(i.relative_to(rel_path)) for i in rel_path.glob('**/*.*')])
    deleting = on_disk - alive_files
    # print(on_disk)
    # print(alive_files)
    print(f"Deleting {len(deleting)} old files", flush=True)
    for i in deleting:
        print("Deleting", i)
        (rel_path/i).unlink()

if __name__ == "__main__":
    here = Path(os.path.abspath(__file__)).parent
    # =================== standalone ==========================
    for v in FEATURE_VERSIONS:
        filelist = set()
        download_release(v, 'hotspot', filelist)
        delete_old_files(v, filelist)
    # =================== APT repos ==========================
    # "$apt_sync" --delete "${BASE_URL}/deb" @ubuntu-lts,@debian-current main amd64,armhf,arm64 "$BASE_PATH/deb"
    sp.run([str(here/"apt-sync.py"),
        '--delete',
        f'{BASE_URL}/deb',
        '@ubuntu-lts,@debian-current',
        'main',
        'amd64,armhf,arm64',
        f"{BASE_PATH}/deb"
        ],
        check=True)
    print("APT finished", flush=True)

    # =================== YUM repos ==========================
    # "$yum_sync" "${BASE_URL}/rpm/rhel/@{os_ver}/@{arch}" 7-9 Adopitum x86_64,aarch64 "rhel@{os_ver}-@{arch}" "$BASE_PATH/rpm"
    sp.run([str(here/"yum-sync.py"),
        BASE_URL+'/rpm/rhel/@{os_ver}/@{arch}',
        "--download-repodata",
        '9',
        'Adoptium',
        'x86_64,aarch64',
        "rhel@{os_ver}-@{arch}",
        f"{BASE_PATH}/rpm"
        ],
        check=True)
    print("YUM finished", flush=True)

