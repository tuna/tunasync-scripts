#!/usr/bin/env python3
import os
import json
import requests
import time
import subprocess as sp
import shutil
from email.utils import parsedate_to_datetime
from pathlib import Path

# mainly from apt-sync.py

FORMULAE_BREW_SH_GITHUB_ACTIONS_ARTIFACT_API = os.getenv("TUNASYNC_UPSTREAM_URL", "https://api.github.com/repos/Homebrew/formulae.brew.sh/actions/artifacts?name=github-pages")
WORKING_DIR = Path(os.getenv("TUNASYNC_WORKING_DIR", "/data"))
DOWNLOAD_TIMEOUT=int(os.getenv('DOWNLOAD_TIMEOUT', '1800'))

github_api_headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

if 'GITHUB_TOKEN' in os.environ:
    github_api_headers['Authorization'] = 'token {}'.format(
        os.environ['GITHUB_TOKEN'])
else:
    # https://github.com/actions/upload-artifact/issues/51
    # the token should have 'public_repo' access
    raise Exception("GITHUB_TOKEN is required")

def formulae_github_pages(zip_file: Path, unzip_directory: Path, tar_directory: Path):
    artifacts = requests.get(FORMULAE_BREW_SH_GITHUB_ACTIONS_ARTIFACT_API, headers=github_api_headers)
    artifacts.raise_for_status()
    artifacts = artifacts.json()
    latest = None
    for artifact in artifacts["artifacts"]:
        if artifact["workflow_run"]["head_branch"] == "master":
            latest = artifact
            break
    zip_url = latest["archive_download_url"]

    check_and_download(zip_url, zip_file, zip_file, github_api_headers)
    sp.run(["unzip", str(zip_file), "-d", str(unzip_directory)])
    sp.run(["tar", "-C", str(tar_directory), "-xf", str(unzip_directory / "artifact.tar")])

def bottles(formula_file: Path):
    b = {}
    formulae = json.load(formula_file.open())
    # refer to https://github.com/ustclug/ustcmirror-images/blob/master/homebrew-bottles/bottles-json/src/main.rs
    for formula in formulae:
        if formula["versions"]["bottle"] and "stable" in formula["bottle"]:
            bs = formula["bottle"]["stable"]
            for (platform, v) in bs["files"].items():
                sha256 = v["sha256"]
                url = v["url"]
                name = formula["name"]
                version = formula["versions"]["stable"]
                revision = "" if formula["revision"] == 0 else f"_{formula['revision']}"
                rebuild = "" if bs["rebuild"] == 0 else f".{bs['rebuild']}"
                file = f"{name}-{version}{revision}.{platform}.bottle{rebuild}.tar.gz"
                b[file] = {
                    "url": url,
                    "sha256": sha256,
                }
    return b

ghcr_headers = {
    "Accept": "application/vnd.oci.image.index.v1+json",
    "Authorization": "Bearer QQ=="
}

# borrowed from apt-sync.py
def check_and_download(url: str, dst_file: Path, dst_tmp_file: Path, headers=ghcr_headers):
    if dst_file.is_file(): return 2 # old file
    try:
        start = time.time()
        with requests.get(url, stream=True, timeout=(5, 10), headers=headers) as r:
            r.raise_for_status()
            if 'last-modified' in r.headers:
                remote_ts = parsedate_to_datetime(
                    r.headers['last-modified']).timestamp()
            else: remote_ts = None

            with dst_tmp_file.open('wb') as f:
                for chunk in r.iter_content(chunk_size=1024**2):
                    if time.time() - start > DOWNLOAD_TIMEOUT:
                        raise TimeoutError("Download timeout")
                    if not chunk: continue # filter out keep-alive new chunks

                    f.write(chunk)
            if remote_ts is not None:
                os.utime(dst_tmp_file, (remote_ts, remote_ts))
        return 0
    except BaseException as e:
        print(e, flush=True)
        if dst_tmp_file.is_file(): dst_tmp_file.unlink()
    return 1

if __name__ == "__main__":
    # clean tmp file from previous sync
    TMP_DIR = WORKING_DIR / ".tmp"

    ZIP_FILE = TMP_DIR / "github-pages.zip"
    UNZIP_DIR = TMP_DIR / "unzip"
    TAR_DIR = TMP_DIR / "github-pages"
    TAR_API_DIR = TAR_DIR / "api"

    FORMULA_FILE = TAR_API_DIR / "formula.json"
    INDEX_FILE = TAR_API_DIR / "index.html"

    API_DIR = WORKING_DIR / "api"
    API_OLD_DIR = WORKING_DIR / "api.old"

    shutil.rmtree(str(TMP_DIR), ignore_errors=True)
    TMP_DIR.mkdir(exist_ok=True, parents=True)
    UNZIP_DIR.mkdir(exist_ok=True)
    TAR_DIR.mkdir(exist_ok=True)

    formulae_github_pages(ZIP_FILE, UNZIP_DIR, TAR_DIR)
    # no homepage
    INDEX_FILE.unlink()

    # download bottles
    b = bottles(FORMULA_FILE)
    for file in b:
        sha256 = b[file]["sha256"]

        print(f"Downloading {file}", flush=True)
        dst_file = WORKING_DIR / file
        dst_tmp_file = TMP_DIR / file
        ret = check_and_download(b[file]["url"], dst_file, dst_tmp_file)
        if ret == 0:
            dst_tmp_file.rename(dst_file)
            print(f"Downloaded {file}", flush=True)
        elif ret == 2:
            print(f"Exists {file}, Skip", flush=True)

    # replace API directory
    print("Replacing API")
    shutil.rmtree(str(API_OLD_DIR), ignore_errors=True)
    if API_DIR.exists():
        API_DIR.rename(API_OLD_DIR)
    TAR_API_DIR.rename(API_DIR)

    files = list(b.keys())
    # garbage collection
    for file in WORKING_DIR.glob("*.tar.gz"):
        if file.name not in files:
            print(f"GC {file.name}", flush=True)
            file.unlink()

    shutil.rmtree(str(API_OLD_DIR), ignore_errors=True)
    shutil.rmtree(str(TMP_DIR), ignore_errors=True)
