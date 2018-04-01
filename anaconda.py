#!/usr/bin/env python3
import os
import json
import hashlib
import tempfile
import shutil
import logging
import subprocess as sp
from pathlib import Path
from email.utils import parsedate_to_datetime

import requests
from pyquery import PyQuery as pq

DEFAULT_CONDA_REPO_BASE = "https://repo.continuum.io"
DEFAULT_CONDA_CLOUD_BASE = "https://conda.anaconda.org"

CONDA_REPO_BASE_URL = os.getenv("CONDA_REPO_URL", "https://repo.continuum.io")
CONDA_CLOUD_BASE_URL = os.getenv("CONDA_COULD_URL", "https://conda.anaconda.org")

WORKING_DIR = os.getenv("TUNASYNC_WORKING_DIR")

CONDA_REPOS = ("main", "free", "r", "mro", "pro")
CONDA_ARCHES = (
    "noarch", "linux-64", "linux-32", "linux-armv6l", "linux-armv7l",
    "linux-ppc64le", "osx-64", "osx-32", "win-64", "win-32"
)

CONDA_CLOUD_REPOS = (
    "conda-forge/linux-64", "conda-forge/osx-64", "conda-forge/win-64", "conda-forge/noarch",
    "msys2/win-64", "msys2/noarch",
    "bioconda/noarch", "bioconda/linux-64", "bioconda/osx-64",
    "menpo/linux-64", "menpo/osx-64", "menpo/win-64", "menpo/win-32", "menpo/noarch",
    "pytorch/linux-64", "pytorch/osx-64", "pytorch/win-64", "pytorch/win-32", "pytorch/noarch", "peterjc123/win-64", "peterjc123/noarch",
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)


def md5_check(file: Path, md5: str=None):
    m = hashlib.md5()
    with file.open('rb') as f:
        while True:
            buf = f.read(1*1024*1024)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest() == md5


def curl_download(remote_url: str, dst_file: Path, md5: str=None):
    sp.check_call([
        "curl", "-o", str(dst_file),
        "-sL", "--remote-time", "--show-error",
        "--fail", remote_url,
    ])
    if md5 and (not md5_check(dst_file, md5)):
        return "MD5 mismatch"


def sync_repo(repo_url: str, local_dir: Path, tmpdir: Path):
    logging.info("Start syncing {}".format(repo_url))
    local_dir.mkdir(parents=True, exist_ok=True)

    repodata_url = repo_url + '/repodata.json'
    bz2_repodata_url = repo_url + '/repodata.json.bz2'

    tmp_repodata = tmpdir / "repodata.json"
    tmp_bz2_repodata = tmpdir / "repodata.json.bz2"

    curl_download(repodata_url, tmp_repodata)
    curl_download(bz2_repodata_url, tmp_bz2_repodata)

    with tmp_repodata.open() as f:
        repodata = json.load(f)

    packages = repodata['packages']
    for filename, meta in packages.items():
        file_size, md5 = meta['size'], meta['md5']

        pkg_url = '/'.join([repo_url, filename])
        dst_file = local_dir / filename

        if dst_file.is_file():
            stat = dst_file.stat()
            local_filesize = stat.st_size

            if file_size == local_filesize:
                logging.info("Skipping {}".format(filename))
                continue

            dst_file.unlink()

        for retry in range(3):
            logging.info("Downloading {}".format(filename))
            err = curl_download(pkg_url, dst_file, md5=md5)
            if err is None:
                break
            logging.error("Failed to download {}: {}".format(filename, err))

    shutil.move(str(tmp_repodata), str(local_dir / "repodata.json"))
    shutil.move(str(tmp_bz2_repodata), str(local_dir / "repodata.json.bz2"))


def sync_installer(repo_url, local_dir: Path):
    logging.info("Start syncing {}".format(repo_url))
    local_dir.mkdir(parents=True, exist_ok=True)

    def remote_list():
        r = requests.get(repo_url)
        d = pq(r.content)
        for tr in d('table').find('tr'):
            tds = pq(tr).find('td')
            if len(tds) != 4:
                continue
            fname = tds[0].find('a').text
            md5 = tds[3].text
            yield (fname, md5)

    for filename, md5 in remote_list():
        pkg_url = "/".join([repo_url, filename])
        dst_file = local_dir / filename

        if dst_file.is_file():
            r = requests.head(pkg_url)
            remote_filesize = int(r.headers['content-length'])
            remote_date = parsedate_to_datetime(r.headers['last-modified'])
            stat = dst_file.stat()
            local_filesize = stat.st_size
            local_mtime = stat.st_mtime

            if remote_filesize == local_filesize and remote_date.timestamp() == local_mtime:
                logging.info("Skipping {}".format(filename))
                continue

            dst_file.unlink()

        for retry in range(3):
            logging.info("Downloading {}".format(filename))
            err = curl_download(pkg_url, dst_file, md5=md5)
            if err is None:
                break
            logging.error("Failed to download {}: {}".format(filename, err))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--working-dir", default=WORKING_DIR)
    args = parser.parse_args()

    if args.working_dir is None:
        raise Exception("Working Directory is None")

    working_dir = Path(args.working_dir)

    for dist in ("archive", "miniconda"):
        remote_url = "{}/{}".format(CONDA_REPO_BASE_URL, dist)
        local_dir = working_dir / dist
        try:
            sync_installer(remote_url, local_dir)
        except Exception:
            logging.exception("Failed to sync installers of {}".format(dist))

    for repo in CONDA_REPOS:
        for arch in CONDA_ARCHES:
            remote_url = "{}/pkgs/{}/{}".format(CONDA_REPO_BASE_URL, repo, arch)
            local_dir = working_dir / "pkgs" / repo / arch

            tmpdir = tempfile.mkdtemp()
            try:
                sync_repo(remote_url, local_dir, Path(tmpdir))
            except Exception:
                logging.exception("Failed to sync repo: {}/{}".format(repo, arch))
            finally:
                shutil.rmtree(tmpdir)

    for repo in CONDA_CLOUD_REPOS:
        remote_url = "{}/{}".format(CONDA_CLOUD_BASE_URL, repo)
        local_dir = working_dir / "cloud" / repo

        tmpdir = tempfile.mkdtemp()
        try:
            sync_repo(remote_url, local_dir, Path(tmpdir))
        except Exception:
            logging.exception("Failed to sync repo: {}/{}".format(repo, arch))
        finally:
            shutil.rmtree(tmpdir)


if __name__ == "__main__":
    main()

# vim: ts=4 sw=4 sts=4 expandtab
