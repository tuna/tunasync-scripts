#!/usr/bin/env python3
"""Golang mirror sync script.

Fetches version list from go.dev API and downloads all files from dl.google.com/go/.
Cleans up stale files that are no longer in the version list.

Stale cleanup is restricted to files matching Go release naming conventions
(go1.*, getgo*) to avoid removing unrelated files that happen to share WORKDIR.
"""
import json
import os
import sys
import hashlib
import subprocess
import re

WORKDIR = os.environ["TUNASYNC_WORKING_DIR"]
BASE_URL = "https://dl.google.com/go/"
API_URL = "https://go.dev/dl/?mode=json&include=all"

# Filenames published by go.dev/dl all start with "go1." or "getgo".
GO_FILENAME_RE = re.compile(r"^(go1\.[\w.\-]+|getgo[\w.\-]*)$")


def fetch_versions():
    """Fetch version list from go.dev API."""
    print("Fetching version list from go.dev...")
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "-m", "60", API_URL],
            capture_output=True, text=True, timeout=90
        )
    except Exception as e:
        print(f"Error: failed to fetch version list: {e}")
        sys.exit(1)
    if result.returncode != 0:
        print(f"Error: curl exit {result.returncode} for {API_URL}: {result.stderr.strip()}")
        sys.exit(1)
    try:
        data = json.loads(result.stdout)
    except Exception as e:
        print(f"Error: failed to parse version list JSON: {e}")
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


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(url, filepath):
    """Download a file via curl. Returns True on success."""
    tmpfile = filepath + ".tmp"
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "-m", "600", "-o", tmpfile, url],
            timeout=630
        )
        if result.returncode == 0:
            os.rename(tmpfile, filepath)
            return True
        print(f"  curl exit {result.returncode} for {url}")
        return False
    except Exception as e:
        print(f"  download error: {e}")
        return False
    finally:
        if os.path.exists(tmpfile):
            try:
                os.remove(tmpfile)
            except OSError:
                pass


def get_remote_size(url):
    """Get remote file size via HEAD request, following redirects."""
    try:
        result = subprocess.run(
            ["curl", "-sIL", "-m", "10", url],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        # With -L there may be multiple header blocks; the last Content-Length wins.
        size = None
        for line in result.stdout.splitlines():
            if line.lower().startswith("content-length:"):
                try:
                    size = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
        return size
    except Exception:
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
        expected_sha = info.get("sha256", "")

        # Skip when the local file already matches the upstream sha256 (or size, if no sha).
        if os.path.isfile(filepath):
            if expected_sha:
                try:
                    if sha256_of(filepath) == expected_sha:
                        skipped += 1
                        continue
                except OSError as e:
                    print(f"  cannot read {filename} for sha check: {e}")
            else:
                remote_size = get_remote_size(url)
                if remote_size is not None and os.path.getsize(filepath) == remote_size:
                    skipped += 1
                    continue

        print(f"Downloading {filename}...")
        if not download_file(url, filepath):
            errors += 1
            print(f"ERROR: failed to download {filename}")
            continue

        # Verify the freshly-downloaded file when we know the expected sha256.
        if expected_sha:
            try:
                actual = sha256_of(filepath)
            except OSError as e:
                errors += 1
                print(f"ERROR: cannot read {filename} after download: {e}")
                continue
            if actual != expected_sha:
                errors += 1
                print(f"ERROR: sha256 mismatch for {filename}: "
                      f"got {actual}, expected {expected_sha}")
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                continue
        downloaded += 1

    print(f"Done. Downloaded: {downloaded}, Skipped: {skipped}, Errors: {errors}")

    # Clean up stale files. Only touch entries that look like Go releases so we
    # never remove unrelated files that happen to live in WORKDIR.
    print("Cleaning up stale files...")
    stale = 0
    for fname in os.listdir(WORKDIR):
        fpath = os.path.join(WORKDIR, fname)
        if not os.path.isfile(fpath):
            continue
        if fname in expected:
            continue
        if not GO_FILENAME_RE.match(fname):
            continue
        print(f"Removing stale file: {fname}")
        try:
            os.remove(fpath)
            stale += 1
        except OSError as e:
            print(f"  failed to remove {fname}: {e}")
    print(f"Removed {stale} stale files.")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
