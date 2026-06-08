#!/usr/bin/env python3
"""
Golang mirror synchronization script.

Downloads Go releases from https://go.dev/dl/ and syncs them to a local directory.
Uses the JSON API at https://go.dev/dl/?mode=json for efficient data retrieval.
"""
import hashlib
import os
import queue
import threading
from pathlib import Path

import requests
from pyquery import PyQuery as pq
from requests import adapters

BASE_URL = os.getenv("TUNASYNC_UPSTREAM_URL", "https://go.dev/dl/")
WORKING_DIR = os.getenv("TUNASYNC_WORKING_DIR")
SYNC_USER_AGENT = os.getenv("SYNC_USER_AGENT", "Go Syncing Tool (https://github.com/tuna/tunasync-scripts)/1.0")

# connect and read timeout value
TIMEOUT_OPTION = (7, 10)
# user agent
requests.utils.default_user_agent = lambda: SYNC_USER_AGENT
# retries
adapters.DEFAULT_RETRIES = 3



class GoRelease:
    """Represents a single Go release file."""
    def __init__(self, filename, os_name, arch, version, sha256, kind):
        self.filename = filename
        self.os = os_name
        self.arch = arch
        self.version = version
        self.sha256 = sha256
        self.kind = kind
        # Optional per-release base URL; falls back to global BASE_URL if not set
        self._base_url = None

    @property
    def base_url(self):
        """
        Base URL used to construct the download URL for this release.
        If not explicitly set, falls back to the global BASE_URL.
        """
        return self._base_url or BASE_URL

    @base_url.setter
    def base_url(self, value):
        self._base_url = value
    
    @property
    def download_url(self):
        return f"{self.base_url.rstrip('/')}/{self.filename}"
    
    @property
    def relative_path(self):
        # Structure: go/{version}/{filename}
        return f"{self.version}/{self.filename}"


class RemoteSite:
    """Handles fetching and parsing Go releases from go.dev."""

    def __init__(self, base_url=BASE_URL, sync_all=False):
        self.base_url = base_url
        self.sync_all = sync_all
        self.releases = []
        self._fetch_releases()

    def _fetch_releases(self):
        """Fetch releases from the JSON API or HTML page."""

        self._fetch_from_json()
        if self.sync_all:
            self._fetch_from_html()

    def _fetch_from_json(self):
        """Fetch releases from the JSON API."""
        json_url = self.base_url.rstrip('/') + "/?mode=json"
        try:
            r = requests.get(json_url, timeout=TIMEOUT_OPTION)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"Panic: failed to fetch release list: {e}")
            import traceback
            traceback.print_exc()
            os._exit(1)

        for release in data:
            version = release.get("version", "")
            files = release.get("files", [])
            for f in files:
                go_release = GoRelease(
                    filename=f.get("filename", ""),
                    os_name=f.get("os", ""),
                    arch=f.get("arch", ""),
                    version=version,
                    sha256=f.get("sha256", ""),
                    kind=f.get("kind", "")
                )
                self.releases.append(go_release)

    def _fetch_from_html(self):
        """Fetch all releases from HTML page by parsing all version directories."""
        try:
            r = requests.get(self.base_url, timeout=TIMEOUT_OPTION)
            r.raise_for_status()
        except Exception as e:
            print(f"Panic: failed to fetch download page: {e}")
            import traceback
            traceback.print_exc()
            os._exit(1)

        releases_xpath = "#archive > div.expanded div.toggle"

        d = pq(r.text)
        version_tags = d(releases_xpath)

        for version_tag in version_tags:
            # Get version from the id attribute (e.g., "go1.26.0")
            version = version_tag.attrib.get('id', '')
            if not version:
                continue

            # Find the download table within this version tag
            table = pq(version_tag)('.downloadtable')
            if not table:
                continue

            # Parse each row in the table body
            rows = table('tr')
            for row in rows[1:]:  # Skip header row
                row_pq = pq(row)

                # Extract filename and download link
                filename_elem = row_pq('td.filename a.download')
                if not filename_elem:
                    continue

                filename = filename_elem.text() or ''

                # Extract other fields from table cells
                cells = row_pq('td')
                if len(cells) < 6:
                    continue

                kind = pq(cells[1]).text() or ''  # Kind (Source, Archive, Installer)
                os_name = str(pq(cells[2]).text() or '')  # OS
                arch = str(pq(cells[3]).text() or '')  # Arch
                sha256_elem = pq(cells[5])('tt')  # SHA256 in <tt> tag
                sha256 = sha256_elem.text() or ''

                # Create the release object
                go_release = GoRelease(
                    filename=filename,
                    os_name=os_name,
                    arch=arch,
                    version=version,
                    sha256=sha256,
                    kind=kind
                )
                self.releases.append(go_release)

    @property
    def files(self):
        """Yield all release files."""
        for release in self.releases:
            yield release


def requests_download(remote_url: str, dst_file: Path):
    """Download a file from the remote URL."""
    with requests.get(remote_url, stream=True, timeout=TIMEOUT_OPTION) as r:
        r.raise_for_status()
        
        tmpfile = dst_file.parent / ("." + dst_file.name + ".tmp")
        with open(tmpfile, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024**2):
                if chunk:
                    f.write(chunk)
        
        # Set modification time if available
        last_modified = r.headers.get('last-modified')
        if last_modified:
            from email.utils import parsedate_to_datetime
            try:
                remote_ts = parsedate_to_datetime(last_modified).timestamp()
                os.utime(tmpfile, (remote_ts, remote_ts))
            except Exception:
                pass
        
        tmpfile.rename(dst_file)


def downloading_worker(q):
    """Worker thread for downloading files."""
    while True:
        item = q.get()
        if item is None:
            break

        release, dst_file, working_dir = item
        try:

            if dst_file.is_file() and release.sha256:
                print(f"checking SHA256 for {dst_file.relative_to(working_dir)}", flush=True)
                local_sha256 = hashlib.sha256(dst_file.read_bytes()).hexdigest()
                if local_sha256 == release.sha256:
                    print(f"skipping (SHA256 match) {dst_file.relative_to(working_dir)}", flush=True)
                    continue

            print(f"downloading {release.download_url}", flush=True)
            requests_download(release.download_url, dst_file)

            # Verify SHA256 after download
            if release.sha256:
                downloaded_sha256 = hashlib.sha256(dst_file.read_bytes()).hexdigest()
                if downloaded_sha256 != release.sha256:
                    print(f"ERROR: SHA256 mismatch for {dst_file.name}", flush=True)
                    dst_file.unlink()
                    raise Exception(f"SHA256 mismatch: expected {release.sha256}, got {downloaded_sha256}")

        except Exception:
            import traceback
            traceback.print_exc()
            print(f"Failed to download {release.download_url if item else 'unknown'}", flush=True)
            if dst_file.is_file():
                try:
                    dst_file.unlink()
                except Exception:
                    pass
        finally:
            q.task_done()


def create_workers(n):
    """Create worker threads for downloading."""
    task_queue = queue.Queue()
    for _ in range(n):
        t = threading.Thread(target=downloading_worker, args=(task_queue,))
        t.start()
    return task_queue


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Go mirror synchronization tool")
    parser.add_argument("--base-url", default=BASE_URL, help="Base URL for Go downloads")
    parser.add_argument("--working-dir", default=WORKING_DIR, help="Working directory for sync")
    parser.add_argument("--workers", default=1, type=int, help='number of concurrent downloading jobs')
    parser.add_argument("--fast-skip", action='store_true',
                        help='do not verify size and SHA256 of existing package files')
    parser.add_argument("--include", default=None,
                        help='comma-separated list of OS/arch to include (e.g., "linux-amd64,darwin-arm64,windows-amd64")')
    parser.add_argument("--exclude", default=None,
                        help='comma-separated list of OS/arch to exclude')
    parser.add_argument("--sync-all", action='store_true',
                        help='sync all versions from HTML page instead of just JSON versions')
    args = parser.parse_args()
    
    if args.working_dir is None:
        raise Exception("Working Directory is None")
    
    working_dir = Path(args.working_dir)
    task_queue = create_workers(args.workers)
    
    # Parse include/exclude filters
    include_filter = None
    if args.include:
        include_filter = set(args.include.split(','))
    
    exclude_filter = None
    if args.exclude:
        exclude_filter = set(args.exclude.split(','))
    
    remote_filelist = []
    rs = RemoteSite(args.base_url, sync_all=args.sync_all)
    
    for release in rs.files:
        # Apply filters
        if include_filter:
            os_arch = f"{release.os}-{release.arch}" if release.os else release.filename
            if os_arch not in include_filter:
                continue
        
        if exclude_filter:
            os_arch = f"{release.os}-{release.arch}" if release.os else release.filename
            if os_arch in exclude_filter:
                continue
        
        dst_file = working_dir / release.relative_path
        remote_filelist.append(dst_file.relative_to(working_dir))
        
        if dst_file.is_file():
            if args.fast_skip:
                # Fast skip: just check if file exists
                print(f"fast skipping {dst_file.relative_to(working_dir)}", flush=True)
                continue
        else:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
        
        task_queue.put((release, dst_file, working_dir))
    
    # Block until all tasks are done
    task_queue.join()
    
    # Stop workers
    for _ in range(args.workers):
        task_queue.put(None)
    
    # Find and delete files that no longer exist on remote
    local_filelist = []
    for local_file in working_dir.glob('**/*'):
        if local_file.is_file():
            local_filelist.append(local_file.relative_to(working_dir))
    
    for old_file in set(local_filelist) - set(remote_filelist):
        print(f"deleting {old_file}", flush=True)
        old_file = working_dir / old_file
        old_file.unlink()
    
    print("Sync completed!", flush=True)


if __name__ == "__main__":
    main()


# vim: ts=4 sw=4 sts=4 expandtab
