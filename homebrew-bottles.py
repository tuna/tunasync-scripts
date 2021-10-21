#!/usr/bin/env python3
import os
import json
import requests
import time
from email.utils import parsedate_to_datetime
from pathlib import Path

# mainly from apt-sync.py

HOMEBREW_BOTTLE_DOMAIN = os.getenv("TUNASYNC_UPSTREAM_URL", "https://formulae.brew.sh/api/formula.json")
WORKING_DIR = Path(os.getenv("TUNASYNC_WORKING_DIR", "/data"))
DOWNLOAD_TIMEOUT=int(os.getenv('DOWNLOAD_TIMEOUT', '1800'))

headers = {
    "Accept": "application/vnd.oci.image.index.v1+json",
    "Authorization": "Bearer QQ=="
}

def bottles():
    b = {}
    r = requests.get(HOMEBREW_BOTTLE_DOMAIN, timeout=(5, 10))
    r.raise_for_status()
    # refer to https://github.com/ustclug/ustcmirror-images/blob/master/homebrew-bottles/bottles-json/src/main.rs
    formulae = r.json()
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

# borrowed from apt-sync.py
def check_and_download(url: str, dst_file: Path, dst_tmp_file: Path):
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
    TMP_DIR.mkdir(exist_ok=True)
    for file in TMP_DIR.glob("*.tar.gz"):
        print(f"Clean tmp file {file.name}", flush=True)
        file.unlink()

    b = bottles()
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

    files = list(b.keys())
    # garbage collection
    for file in WORKING_DIR.glob("*.tar.gz"):
        if file.name not in files:
            print(f"GC {file.name}", flush=True)
            file.unlink()
