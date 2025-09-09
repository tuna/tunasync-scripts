#!/usr/bin/env python3

import concurrent.futures
import hashlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

BASE_URL = os.getenv("TUNASYNC_UPSTREAM_URL", "https://pub.dev")
WORKING_DIR = os.getenv("TUNASYNC_WORKING_DIR")
MIRROR_URL = os.getenv("MIRROR_BASE_URL", "https://mirrors.tuna.tsinghua.edu.cn/dart-pub")
REPOS = []
UA = 'tuna-pub-mirror/0.0 (+https://github.com/tuna/tunasync-scripts)'


# wrap around requests.get to use token if available
def get_with_token(*args, **kwargs):
    headers = kwargs["headers"] if "headers" in kwargs else {}
    if "PUB_TOKEN" in os.environ:
        headers["Authorization"] = "Bearer {}".format(os.environ["PUB_TOKEN"])
    headers["User-Agent"] = UA
    kwargs["headers"] = headers
    return requests.get(*args, **kwargs)


def do_download(remote_url: str, dst_file: Path, sha256: Optional[str] = None):
    # NOTE the stream=True parameter below
    with get_with_token(remote_url, stream=True) as r:
        r.raise_for_status()
        tmp_dst_file = None
        try:
            downloaded_sha256 = hashlib.sha256()
            with tempfile.NamedTemporaryFile(
                prefix="." + dst_file.name + ".",
                suffix=".tmp",
                dir=dst_file.parent,
                delete=False,
            ) as f:
                tmp_dst_file = Path(f.name)
                for chunk in r.iter_content(chunk_size=1024**2):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        downloaded_sha256.update(chunk)
                        # f.flush()
            # check for downloaded sha256
            if sha256 and sha256 != downloaded_sha256.hexdigest():
                raise Exception(
                    f"File {dst_file.as_posix()} sha256 mismatch: downloaded {downloaded_sha256.hexdigest()}, expected {sha256}"
                )
            tmp_dst_file.chmod(0o644)
            tmp_dst_file.replace(dst_file)
        finally:
            if tmp_dst_file is not None:
                if tmp_dst_file.is_file():
                    tmp_dst_file.unlink()


def download_pkg_ver(
    pkg_name: str, working_dir: Path, ver: str, url: str, sha256: str
) -> bool:
    # download archive file to /packages/<pkg>/versions/<version>.tar.gz
    dst_file = working_dir / "packages" / pkg_name / "versions" / f"{ver}.tar.gz"
    if not dst_file.is_file():
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading {url} to {dst_file.as_posix()}")
        try:
            do_download(url, dst_file, sha256=sha256)
            return True
        except Exception as e:
            logger.error(f"Failed to download {url} to {dst_file.as_posix()}: {e}")
            return False
    else:
        logger.info(f"File {dst_file.as_posix()} already exists, skipping download")
        return True


# https://github.com/dart-lang/pub/blob/master/doc/repository-spec-v2.md#list-all-versions-of-a-package
def handle_pkg(
    executor: concurrent.futures.ThreadPoolExecutor,
    base_url: str,
    pkg_name: str,
    working_dir: Path,
    mirror_url: str,
    clean: bool,
) -> bool:

    logger.info(f"Handling package {pkg_name}...")
    # fetch metadata from upstream
    pkgUrl = base_url + "/api/packages/" + pkg_name
    req = get_with_token(pkgUrl, headers={"Accept": "application/vnd.pub.v2+json"}, timeout=5)
    req.raise_for_status()
    resp = req.json()

    download_tasks = []
    latest_ver = resp["latest"]["version"]

    for ver in resp["versions"]:
        logger.debug(f'Checking {pkg_name}=={ver["version"]}')
        if "advisoriesUpdated" in ver:
            del ver["advisoriesUpdated"] # not supported
        if ver.get("retracted", False):
            logger.info(f'Skipping retracted version {pkg_name}=={ver["version"]}')
            dst_file = working_dir / "packages" / pkg_name / "versions" / f'{ver["version"]}.tar.gz'
            dst_file.unlink(missing_ok=True)
            continue
        download_tasks.append(
            (
                pkg_name,
                working_dir,
                ver["version"],
                ver["archive_url"],
                ver["archive_sha256"],
            )
        )
        # replace URL in metadata with our mirror URL
        cur_ver = ver["version"]
        serving_url = f"{mirror_url}/packages/{pkg_name}/versions/{cur_ver}.tar.gz"
        ver["archive_url"] = serving_url
        if cur_ver == latest_ver:
            resp["latest"] = ver

    # clean up obsolete versions if needed
    if clean:
        all_versions = [ver["version"] for ver in resp["versions"] if not ver.get("retracted", False)]
        versions_dir = working_dir / "packages" / pkg_name / "versions"
        if versions_dir.is_dir():
            for f in versions_dir.iterdir():
                if f.is_file() and f.suffix == ".gz":
                    ver = f.stem
                    if ver not in all_versions:
                        logger.info(f"Removing obsolete pkg file {f.as_posix()}")
                        f.unlink(missing_ok=True)

    # save modified metadata to api/packages/<pkg>/meta.json
    modified_meta_str = json.dumps(ver)
    meta_on_disk = working_dir / "api" / "packages" / pkg_name / "meta.json"
    # fast path: check if meta.json exists and has the same size
    if not meta_on_disk.is_file() or meta_on_disk.stat().st_size != len(
        modified_meta_str
    ):
        logger.info(
            f"Metadata for package {pkg_name} is outdated or missing, updating..."
        )
        # download all versions concurrently
        results = list(executor.map(lambda p: download_pkg_ver(*p), download_tasks))
        if not all(results):
            logger.error(
                f"Failed to download some versions of package {pkg_name}, skipping metadata update"
            )
            return False
        meta_on_disk.parent.mkdir(parents=True, exist_ok=True)
        with open(meta_on_disk, "w", encoding="utf-8") as f:
            f.write(modified_meta_str)
            f.flush()
    else:
        logger.info(
            f"Metadata for package {pkg_name} is up to date (latest {latest_ver}), skipping"
        )

    return True


def main():

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--mirror-url", default=MIRROR_URL)
    parser.add_argument("--working-dir", default=WORKING_DIR)
    parser.add_argument(
        "--workers", default=1, type=int, help="number of concurrent downloading jobs"
    )
    parser.add_argument(
        "--clean",
        action='store_true',
        help="remove obsolete package versions that are no longer in upstream",
    )
    # parser.add_argument("--fast-skip", action='store_true',
    #                     help='do not verify sha256 of existing files')
    args = parser.parse_args()

    if args.working_dir is None:
        raise Exception("Working Directory is None")

    working_dir = Path(args.working_dir)
    base_url = args.base_url
    mirror_url = MIRROR_URL
    clean = args.clean

    logger.info(f"Using upstream URL: {base_url}")
    logger.info(f"Using mirror URL: {mirror_url}")
    logger.info(f"Using working directory: {working_dir.as_posix()}")
    logger.info(f"Using {args.workers} workers")
    logger.info(f"Clean obsolete packages: {'Yes' if clean else 'No'}")

    pkg_executor = concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)
    download_executor = concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)

    # iterate through all packages
    pkgs_url = base_url + "/api/package-names"
    pkg_futures = []
    all_pkgs = []
    while True:
        req = get_with_token(pkgs_url, headers={"Accept-Encoding": "gzip"}, timeout=5)
        req.raise_for_status()
        resp = req.json()

        for pkg in resp["packages"]:
            pkg_futures.append(
                pkg_executor.submit(
                    handle_pkg,
                    download_executor,
                    base_url,
                    pkg,
                    working_dir,
                    mirror_url,
                    clean,
                )
            )
            all_pkgs.append(pkg)

        # null means no more pages
        if not (pkgs_url := resp["nextUrl"]):
            break

    pkg_executor.shutdown(wait=True)

    if clean:
        # clean up obsolete packages
        pkgs_dir = working_dir / "packages"
        if pkgs_dir.is_dir():
            for p in pkgs_dir.iterdir():
                if p.is_dir():
                    pkg_name = p.name
                    if pkg_name not in all_pkgs:
                        logger.info(f"Removing obsolete package {pkg_name}")
                        shutil.rmtree(p, ignore_errors=True)


if __name__ == "__main__":
    main()
