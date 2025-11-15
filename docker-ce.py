#!/usr/bin/env python3
import os
import sys
import threading
import queue
import traceback
from pathlib import Path
from email.utils import parsedate_to_datetime
import re
import traceback

import requests
from pyquery import PyQuery as pq


BASE_URL = os.getenv("TUNASYNC_UPSTREAM_URL", "https://download.docker.com/")
WORKING_DIR = os.getenv("TUNASYNC_WORKING_DIR")
SYNC_USER_AGENT = os.getenv("SYNC_USER_AGENT", "Docker-ce Syncing Tool (https://github.com/tuna/tunasync-scripts)/1.0")

# connect and read timeout value
TIMEOUT_OPTION = (7, 10)
# user agent
requests.utils.default_user_agent = lambda: SYNC_USER_AGENT
# retries
requests.adapters.DEFAULT_RETRIES = 3

REL_URL_RE = re.compile(r"https?:\/\/.+?\/(.+?)(\/index\.html)?$")


class RemoteSite:

    def __init__(self, base_url=BASE_URL):
        if not base_url.endswith('/'):
            base_url = base_url + '/'
        self.base_url = base_url
        self.meta_urls = []

    def is_metafile_url(self, url):
        deb_dists = ('debian', 'ubuntu', 'raspbian')
        rpm_dists = ('fedora', 'centos')

        for dist in deb_dists:
            if '/'+dist+'/' not in url:
                continue
            if '/Contents-' in url:
                return True
            if '/binary-' in url:
                return True
            if 'Release' in url:
                return True

        for dist in rpm_dists:
            if '/'+dist+'/' not in url:
                continue
            if '/repodata/' in url:
                return True

        return False

    def recursive_get_filelist(self, base_url, filter_meta=False):
        if not base_url.endswith('/'):
            yield base_url
            return

        try:
            r = requests.get(base_url, timeout=TIMEOUT_OPTION)
            if r.url != base_url:
                # redirection?
                # handling CentOS/RHEL directory 30x
                target_dir = r.url.split("/")[-2]
                origin_dir = base_url.split("/")[-2]
                if target_dir != origin_dir:
                    # here we create a symlink on the fly
                    from_dir = REL_URL_RE.findall(base_url)[0][0]
                    to_dir = REL_URL_RE.findall(r.url)[0][0]
                    yield (from_dir, to_dir)  # tuple -> create symlink
                    return
        except Exception as e:
            print("Panic: failed to get file list")
            traceback.print_exc()
            os._exit(1)
        if not r.ok:
            return

        d = pq(r.text)
        for link in d('a'):
            if link.text.startswith('..'):
                continue
            href = base_url + link.text
            if filter_meta and self.is_metafile_url(href):
                self.meta_urls.append(href)
            elif link.text.endswith('/'):
                yield from self.recursive_get_filelist(href, filter_meta=filter_meta)
            else:
                yield href

    def relpath(self, url):
        assert url.startswith(self.base_url)
        return url[len(self.base_url):]

    @property
    def files(self):
        yield from self.recursive_get_filelist(self.base_url, filter_meta=True)
        for url in self.meta_urls:
            yield from self.recursive_get_filelist(url, filter_meta=False)


def requests_download(remote_url: str, dst_file: Path):
    # NOTE the stream=True parameter below
    with requests.get(remote_url, stream=True) as r:
        r.raise_for_status()
        remote_ts = parsedate_to_datetime(
            r.headers['last-modified']).timestamp()
        with open(dst_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024**2):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    # f.flush()
        os.utime(dst_file, (remote_ts, remote_ts))


def downloading_worker(q):
    while True:
        item = q.get()
        if item is None:
            break

        try:
            url, dst_file, working_dir = item
            if dst_file.is_file():
                print("checking", url, flush=True)
                r = requests.head(url, timeout=TIMEOUT_OPTION, allow_redirects=True)
                remote_filesize = int(r.headers['content-length'])
                remote_date = parsedate_to_datetime(r.headers['last-modified'])
                stat = dst_file.stat()
                local_filesize = stat.st_size
                local_mtime = stat.st_mtime

                if remote_filesize == local_filesize and remote_date.timestamp() == local_mtime:
                    print("skipping", dst_file.relative_to(working_dir), flush=True)
                    continue

                dst_file.unlink()
            print("downloading", url, flush=True)
            requests_download(url, dst_file)
        except Exception:
            traceback.print_exc()
            print("Failed to download", url, flush=True)
            if dst_file.is_file():
                dst_file.unlink()
        finally:
            q.task_done()


def create_workers(n):
    task_queue = queue.Queue()
    for i in range(n):
        t = threading.Thread(target=downloading_worker, args=(task_queue, ))
        t.start()
    return task_queue

def create_symlink(from_dir: Path, to_dir: Path):
    to_dir = to_dir.relative_to(from_dir.parent)
    if from_dir.exists():
        if from_dir.is_symlink():
            resolved_symlink = from_dir.resolve().relative_to(from_dir.parent.absolute())
            if resolved_symlink != to_dir:
                print(f"WARN: The symlink {from_dir} dest changed from {resolved_symlink} to {to_dir}.")
        else:
            print(f"WARN: The symlink {from_dir} exists on disk but it is not a symlink.")
    else:
        if from_dir.is_symlink():
            print(f"WARN: The symlink {from_dir} is probably invalid.")
        else:
            # create a symlink
            from_dir.parent.mkdir(parents=True, exist_ok=True)
            from_dir.symlink_to(to_dir)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--working-dir", default=WORKING_DIR)
    parser.add_argument("--workers", default=1, type=int,
                        help='number of concurrent downloading jobs')
    parser.add_argument("--fast-skip", action='store_true',
                        help='do not verify size and timestamp of existing package files')
    args = parser.parse_args()

    if args.working_dir is None:
        raise Exception("Working Directory is None")

    working_dir = Path(args.working_dir)
    task_queue = create_workers(args.workers)

    remote_filelist = []
    rs = RemoteSite(args.base_url)
    for url in rs.files:
        if isinstance(url, tuple):
            from_dir, to_dir = url
            create_symlink(working_dir / from_dir, working_dir / to_dir)
        else:
            dst_file = working_dir / rs.relpath(url)
            remote_filelist.append(dst_file.relative_to(working_dir))

            if dst_file.is_file():
                if args.fast_skip and dst_file.suffix in ['.rpm', '.deb', '.tgz', '.zip']:
                    print("fast skipping", dst_file.relative_to(working_dir), flush=True)
                    continue
            else:
                dst_file.parent.mkdir(parents=True, exist_ok=True)

            task_queue.put((url, dst_file, working_dir))

    # block until all tasks are done
    task_queue.join()
    # stop workers
    for i in range(args.workers):
        task_queue.put(None)

    local_filelist = []
    for local_file in working_dir.glob('**/*'):
        if local_file.is_file():
            local_filelist.append(local_file.relative_to(working_dir))

    for old_file in set(local_filelist) - set(remote_filelist):
        print("deleting", old_file, flush=True)
        old_file = working_dir / old_file
        old_file.unlink()


if __name__ == "__main__":
    main()


# vim: ts=4 sw=4 sts=4 expandtab
