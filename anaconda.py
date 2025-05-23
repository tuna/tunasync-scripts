#!/usr/bin/env python3
import hashlib
import json
import logging
import os
import sys
import errno
import random
import shutil
import subprocess as sp
import tempfile
from email.utils import parsedate_to_datetime
from pathlib import Path

from pyquery import PyQuery as pq

import requests


DEFAULT_CONDA_REPO_BASE = "https://repo.continuum.io"
DEFAULT_CONDA_CLOUD_BASE = "https://conda.anaconda.org"

CONDA_REPO_BASE_URL = os.getenv("CONDA_REPO_URL", "https://repo.continuum.io")
CONDA_CLOUD_BASE_URL = os.getenv("CONDA_COULD_URL", "https://conda.anaconda.org")

WORKING_DIR = os.getenv("TUNASYNC_WORKING_DIR")

# fmt: off
CONDA_REPOS = ("main", "free", "r", "msys2")
CONDA_ARCHES = (
    "noarch", "linux-64", "linux-32", "linux-aarch64", "linux-armv6l", "linux-armv7l",
    "linux-ppc64le", "osx-64", "osx-32", "osx-arm64", "win-64", "win-32"
)

CONDA_CLOUD_REPOS = (
    "conda-forge/noarch",          "conda-forge/linux-64",        "conda-forge/linux-aarch64",   "conda-forge/win-64",                                         "conda-forge/osx-64",          "conda-forge/osx-arm64",
    "rapidsai/noarch",             "rapidsai/linux-64",           "rapidsai/linux-aarch64",
    "bioconda/noarch",             "bioconda/linux-64",           "bioconda/linux-aarch64",      "bioconda/win-64",                                            "bioconda/osx-64",             "bioconda/osx-arm64",
    "menpo/noarch",                "menpo/linux-64",                                             "menpo/win-64",                "menpo/win-32",                "menpo/osx-64",
    "pytorch/noarch",              "pytorch/linux-64",            "pytorch/linux-aarch64",       "pytorch/win-64",              "pytorch/win-32",              "pytorch/osx-64",              "pytorch/osx-arm64",
    "pytorch-lts/noarch",          "pytorch-lts/linux-64",                                       "pytorch-lts/win-64",
    "pytorch-test/noarch",         "pytorch-test/linux-64",       "pytorch-test/linux-aarch64",  "pytorch-test/win-64",         "pytorch-test/win-32",         "pytorch-test/osx-64",         "pytorch-test/osx-arm64",
    "stackless/noarch",            "stackless/linux-64",                                         "stackless/win-64",            "stackless/win-32",            "stackless/osx-64",
    "fermi/noarch",                "fermi/linux-64",                                             "fermi/win-64",                                               "fermi/osx-64",                "fermi/osx-arm64",
    "fastai/noarch",               "fastai/linux-64",                                            "fastai/win-64",                                              "fastai/osx-64",
    "omnia/noarch",                "omnia/linux-64",                                             "omnia/win-64",                                               "omnia/osx-64",
    "simpleitk/noarch",            "simpleitk/linux-64",                                         "simpleitk/win-64",            "simpleitk/win-32",            "simpleitk/osx-64",
    "caffe2/noarch",               "caffe2/linux-64",                                            "caffe2/win-64",                                              "caffe2/osx-64",
    "plotly/noarch",               "plotly/linux-64",                                            "plotly/win-64",               "plotly/win-32",               "plotly/osx-64",
    "auto/noarch",                 "auto/linux-64",                                              "auto/win-64",                 "auto/win-32",                 "auto/osx-64",
    "ursky/noarch",                "ursky/linux-64",                                                                                                           "ursky/osx-64",
    "matsci/noarch",               "matsci/linux-64",                                            "matsci/win-64",                                              "matsci/osx-64",
    "psi4/noarch",                 "psi4/linux-64",                                              "psi4/win-64",                                                "psi4/osx-64",
    "Paddle/noarch",               "Paddle/linux-64",                                            "Paddle/win-64",               "Paddle/win-32",               "Paddle/osx-64",               "Paddle/osx-arm64",
    "deepmodeling/noarch",         "deepmodeling/linux-64",
    "numba/noarch",                "numba/linux-64",              "numba/linux-aarch64",         "numba/win-64",                "numba/win-32",                "numba/osx-64",                "numba/osx-arm64",
    "numba/label/dev/noarch",                                                                    "numba/label/dev/win-64",
    "pyviz/noarch",                "pyviz/linux-64",                                             "pyviz/win-64",                "pyviz/win-32",                "pyviz/osx-64",
    "dglteam/noarch",              "dglteam/linux-64",            "dglteam/linux-aarch64",       "dglteam/win-64",                                             "dglteam/osx-64",
    "rdkit/noarch",                "rdkit/linux-64",                                             "rdkit/win-64",                                               "rdkit/osx-64",
    "mordred-descriptor/noarch",   "mordred-descriptor/linux-64",                                "mordred-descriptor/win-64",   "mordred-descriptor/win-32",   "mordred-descriptor/osx-64",
    "ohmeta/noarch",               "ohmeta/linux-64",
    "qiime2/noarch",               "qiime2/linux-64",                                                                                                          "qiime2/osx-64",
    "biobakery/noarch",            "biobakery/linux-64",                                                                                                       "biobakery/osx-64",
    "c4aarch64/noarch",                                           "c4aarch64/linux-aarch64",
    "pytorch3d/noarch",            "pytorch3d/linux-64",
    "idaholab/noarch",             "idaholab/linux-64",
)

EXCLUDED_PACKAGES = (
    "pytorch-nightly", "pytorch-nightly-cpu", "ignite-nightly",
)
# fmt: on

# connect and read timeout value
TIMEOUT_OPTION = (7, 10)

# Generate gzip archive for json files, size threshold
GEN_METADATA_JSON_GZIP_THRESHOLD = 1024 * 1024

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)


def sizeof_fmt(num, suffix="iB"):
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < 1024.0:
            return "%3.2f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.2f%s%s" % (num, "Y", suffix)


def md5_check(file: Path, md5: str = None):
    m = hashlib.md5()
    with file.open("rb") as f:
        while True:
            buf = f.read(1 * 1024 * 1024)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest() == md5


def sha256_check(file: Path, sha256: str = None):
    m = hashlib.sha256()
    with file.open("rb") as f:
        while True:
            buf = f.read(1 * 1024 * 1024)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest() == sha256


def curl_download(remote_url: str, dst_file: Path, sha256: str = None, md5: str = None):
    # fmt: off
    sp.check_call(
        [
            "curl", "-o", str(dst_file),
            "-sL", "--remote-time", "--show-error",
            "--fail", "--retry", "10",
            "--speed-time", "15",
            "--speed-limit", "5000",
            remote_url,
        ]
    )
    # fmt: on
    if sha256 and (not sha256_check(dst_file, sha256)):
        return "SHA256 mismatch"
    if md5 and (not md5_check(dst_file, md5)):
        return "MD5 mismatch"


def sync_repo(
    repo_url: str, local_dir: Path, tmpdir: Path, delete: bool, remove_legacy: bool
):
    logging.info("Start syncing {}".format(repo_url))
    local_dir.mkdir(parents=True, exist_ok=True)

    repodata_url = repo_url + "/repodata.json"
    bz2_repodata_url = repo_url + "/repodata.json.bz2"
    # https://github.com/conda/conda/issues/13256, from conda 24.1.x
    zst_repodata_url = repo_url + "/repodata.json.zst"
    # https://docs.conda.io/projects/conda-build/en/latest/release-notes.html
    # "current_repodata.json" - like repodata.json, but only has the newest version of each file
    current_repodata_url = repo_url + "/current_repodata.json"

    tmp_repodata = tmpdir / "repodata.json"
    tmp_bz2_repodata = tmpdir / "repodata.json.bz2"
    tmp_zst_repodata = tmpdir / "repodata.json.zst"
    tmp_current_repodata = tmpdir / "current_repodata.json"

    curl_download(repodata_url, tmp_repodata)
    curl_download(bz2_repodata_url, tmp_bz2_repodata)
    try:
        curl_download(zst_repodata_url, tmp_zst_repodata)
    except:
        pass
    try:
        curl_download(current_repodata_url, tmp_current_repodata)
    except:
        pass

    with tmp_repodata.open() as f:
        repodata = json.load(f)

    remote_filelist = []
    total_size = 0
    legacy_packages = repodata["packages"]
    conda_packages = repodata.get("packages.conda", {})
    if remove_legacy:
        # https://github.com/anaconda/conda/blob/0dbf85e0546e0b0dc060c8265ec936591ccbe980/conda/core/subdir_data.py#L440-L442
        use_legacy_packages = set(legacy_packages.keys()) - set(
            k[:-6] + ".tar.bz2" for k in conda_packages.keys()
        )
        legacy_packages = {k: legacy_packages[k] for k in use_legacy_packages}
    packages = {**legacy_packages, **conda_packages}

    for filename, meta in packages.items():
        if meta["name"] in EXCLUDED_PACKAGES:
            continue

        file_size = meta["size"]
        # prefer sha256 over md5
        sha256 = None
        md5 = None
        if "sha256" in meta:
            sha256 = meta["sha256"]
        elif "md5" in meta:
            md5 = meta["md5"]
        total_size += file_size

        pkg_url = "/".join([repo_url, filename])
        dst_file = local_dir / filename
        dst_file_wip = local_dir / (".downloading." + filename)
        remote_filelist.append(dst_file)

        if dst_file.is_file():
            stat = dst_file.stat()
            local_filesize = stat.st_size

            if file_size == local_filesize:
                logging.info("Skipping {}".format(filename))
                continue

            dst_file.unlink()

        for retry in range(3):
            logging.info("Downloading {}".format(filename))
            try:
                err = curl_download(pkg_url, dst_file_wip, sha256=sha256, md5=md5)
                if err is None:
                    dst_file_wip.rename(dst_file)
            except sp.CalledProcessError:
                err = "CalledProcessError"
            if err is None:
                break
            logging.error("Failed to download {}: {}".format(filename, err))

    if os.path.getsize(tmp_repodata) > GEN_METADATA_JSON_GZIP_THRESHOLD:
        sp.check_call(["gzip", "--no-name", "--keep", "--", str(tmp_repodata)])
        shutil.move(str(tmp_repodata) + ".gz", str(local_dir / "repodata.json.gz"))
    else:
        # If the gzip file is not generated, remove the dangling gzip archive
        Path(local_dir / "repodata.json.gz").unlink(missing_ok=True)

    shutil.move(str(tmp_repodata), str(local_dir / "repodata.json"))
    shutil.move(str(tmp_bz2_repodata), str(local_dir / "repodata.json.bz2"))
    try:
        shutil.move(str(tmp_zst_repodata), str(local_dir / "repodata.json.zst"))
    except:
        pass
    tmp_current_repodata_gz_gened = False
    if tmp_current_repodata.is_file():
        if os.path.getsize(tmp_current_repodata) > GEN_METADATA_JSON_GZIP_THRESHOLD:
            sp.check_call(
                ["gzip", "--no-name", "--keep", "--", str(tmp_current_repodata)]
            )
            shutil.move(
                str(tmp_current_repodata) + ".gz",
                str(local_dir / "current_repodata.json.gz"),
            )
            tmp_current_repodata_gz_gened = True
        shutil.move(str(tmp_current_repodata), str(local_dir / "current_repodata.json"))
    if not tmp_current_repodata_gz_gened:
        # If the gzip file is not generated, remove the dangling gzip archive
        Path(local_dir / "current_repodata.json.gz").unlink(missing_ok=True)

    if delete:
        local_filelist = []
        delete_count = 0
        for i in local_dir.glob("*.tar.bz2"):
            local_filelist.append(i)
        for i in local_dir.glob("*.conda"):
            local_filelist.append(i)
        for i in set(local_filelist) - set(remote_filelist):
            logging.info("Deleting {}".format(i))
            i.unlink()
            delete_count += 1
        logging.info("{} files deleted".format(delete_count))

    logging.info(
        "{}: {} files, {} in total".format(
            repodata_url, len(remote_filelist), sizeof_fmt(total_size)
        )
    )
    return total_size


def sync_installer(repo_url, local_dir: Path):
    logging.info("Start syncing {}".format(repo_url))
    local_dir.mkdir(parents=True, exist_ok=True)
    full_scan = random.random() < 0.1  # Do full version check less frequently
    scan_futher = True

    def remote_list():
        r = requests.get(repo_url, timeout=TIMEOUT_OPTION)
        d = pq(r.content)
        for tr in d("table").find("tr"):
            tds = pq(tr).find("td")
            if len(tds) != 4:
                continue
            fname = tds[0].find("a").text
            sha256 = tds[3].text
            if sha256 == "<directory>" or len(sha256) != 64:
                continue
            yield (fname, sha256)

    for filename, sha256 in remote_list():
        pkg_url = "/".join([repo_url, filename])
        dst_file = local_dir / filename
        dst_file_wip = local_dir / (".downloading." + filename)

        if dst_file.is_file():
            if not scan_futher:
                logging.info("Skipping {} without checking".format(filename))
                continue
            r = requests.head(pkg_url, allow_redirects=True, timeout=TIMEOUT_OPTION)
            len_avail = "content-length" in r.headers
            if len_avail:
                remote_filesize = int(r.headers["content-length"])
            remote_date = parsedate_to_datetime(r.headers["last-modified"])
            stat = dst_file.stat()
            local_filesize = stat.st_size
            local_mtime = stat.st_mtime

            # Do content verification on ~5% of files (see issue #25)
            if (
                (not len_avail or remote_filesize == local_filesize)
                and remote_date.timestamp() == local_mtime
                and (random.random() < 0.95 or sha256_check(dst_file, sha256))
            ):
                logging.info("Skipping {}".format(filename))

                # Stop the scanning if the most recent version is present
                if not full_scan:
                    logging.info("Stop the scanning")
                    scan_futher = False

                continue

            logging.info("Removing {}".format(filename))
            dst_file.unlink()

        for retry in range(3):
            logging.info("Downloading {}".format(filename))
            err = ""
            try:
                err = curl_download(pkg_url, dst_file_wip, sha256=sha256)
                if err is None:
                    dst_file_wip.rename(dst_file)
            except sp.CalledProcessError:
                err = "CalledProcessError"
            if err is None:
                break
            logging.error("Failed to download {}: {}".format(filename, err))


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--working-dir", default=WORKING_DIR)
    parser.add_argument(
        "--delete", action="store_true", help="delete unreferenced package files"
    )
    parser.add_argument(
        "--remove-legacy",
        action="store_true",
        help="delete legacy packages which have conda counterpart. Requires client conda >= 4.7.0",
    )
    args = parser.parse_args()

    if args.working_dir is None:
        raise Exception("Working Directory is None")

    working_dir = Path(args.working_dir)
    size_statistics = 0
    random.seed()

    success = True

    logging.info("Syncing installers...")
    for dist in ("archive", "miniconda"):
        remote_url = "{}/{}".format(CONDA_REPO_BASE_URL, dist)
        local_dir = working_dir / dist
        try:
            sync_installer(remote_url, local_dir)
            size_statistics += sum(
                f.stat().st_size for f in local_dir.glob("*") if f.is_file()
            )
        except Exception:
            logging.exception("Failed to sync conda installers: {}".format(dist))
            success = False

    for repo in CONDA_REPOS:
        for arch in CONDA_ARCHES:
            remote_url = "{}/pkgs/{}/{}".format(CONDA_REPO_BASE_URL, repo, arch)
            local_dir = working_dir / "pkgs" / repo / arch

            tmpdir = tempfile.mkdtemp()
            try:
                size_statistics += sync_repo(
                    remote_url, local_dir, Path(tmpdir), args.delete, args.remove_legacy
                )
            except Exception:
                logging.exception("Failed to sync conda repo: {}/{}".format(repo, arch))
                # success = False # some arch might not exist, do not fail
            finally:
                shutil.rmtree(tmpdir)

    for repo in CONDA_CLOUD_REPOS:
        remote_url = "{}/{}".format(CONDA_CLOUD_BASE_URL, repo)
        local_dir = working_dir / "cloud" / repo

        tmpdir = tempfile.mkdtemp()
        try:
            size_statistics += sync_repo(
                remote_url, local_dir, Path(tmpdir), args.delete, args.remove_legacy
            )
        except Exception:
            logging.exception("Failed to sync conda cloud repo: {}".format(repo))
            success = False
        finally:
            shutil.rmtree(tmpdir)

    print("Total size is", sizeof_fmt(size_statistics, suffix=""))
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()

# vim: ts=4 sw=4 sts=4 expandtab
