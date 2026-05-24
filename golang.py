#!/usr/bin/env python3
"""Golang mirror sync script.

Fetches version list from go.dev API and downloads all files from dl.google.com/go/.
Cleans up stale files that are no longer in the version list.
"""
import json
import os
import sys
import subprocess
import hashlib

WORKDIR = os.environ["TUNASYNC_WORKING_DIR"]
BASE_URL = "https://dl.google.com/go/"
API_URL = "https://go.dev/dl/?mode=json&include=all"


def fetch_versions():
    """Fetch version list from go.dev API."""
    print("Fetching version list from go.dev...")
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "60", API_URL],
            capture_output=True, text=True, timeout=90
        )
        data = json.loads(result.stdout)
    except Exception as e:
        print(f"Error: failed to fetch version list: {e}")
        sys.exit(1)

    files = {}
    for v in data:
        for f in v.get("files", []):
            filename = f["filename"]
            sha256 = f.get("sha256", "")
            files[filename] = {
                "url": BASE_URL + filename,
                "sha256": sha256,
            }
    return files


def download_file(filename, url, filepath):
    """Download a file if not present or size mismatch."""
    tmpfile = filepath + ".tmp"
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "-m", "600", "-o", tmpfile, url],
            timeout=630
        )
        if result.returncode == 0:
            os.rename(tmpfile, filepath)
            return True
        else:
            if os.path.exists(tmpfile):
                os.remove(tmpfile)
            return False
    except Exception:
        if os.path.exists(tmpfile):
            os.remove(tmpfile)
        return False


def get_remote_size(url):
    """Get remote file size via HEAD request."""
    try:
        result = subprocess.run(
            ["curl", "-sI", "-m", "10", url],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines():
            if line.lower().startswith("content-length:"):
                return int(line.split(":", 1)[1].strip())
    except Exception:
        pass
    return None


def main():
    os.makedirs(WORKDIR, exist_ok=True)
    os.chdir(WORKDIR)

    expected = fetch_versions()
    print(f"Total files to sync: {len(expected)}")

    downloaded = 0
    skipped = 0
    errors = 0

    for filename, info in expected.items():
        filepath = os.path.join(WORKDIR, filename)
        url = info["url"]

        # Check if file exists and has correct size
        if os.path.isfile(filepath):
            remote_size = get_remote_size(url)
            if remote_size is not None:
                local_size = os.path.getsize(filepath)
                if local_size == remote_size:
                    skipped += 1
                    continue

        print(f"Downloading {filename}...")
        if download_file(filename, url, filepath):
            downloaded += 1
        else:
            errors += 1
            print(f"ERROR: failed to download {filename}")

    print(f"Done. Downloaded: {downloaded}, Skipped: {skipped}, Errors: {errors}")

    # Clean up stale files
    print("Cleaning up stale files...")
    stale = 0
    for fname in os.listdir(WORKDIR):
        fpath = os.path.join(WORKDIR, fname)
        if os.path.isfile(fpath) and fname not in expected:
            print(f"Removing stale file: {fname}")
            os.remove(fpath)
            stale += 1
    print(f"Removed {stale} stale files.")


if __name__ == "__main__":
    main()
