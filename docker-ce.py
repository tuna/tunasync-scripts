#!/usr/bin/env python3
import os
import subprocess as sp
from pathlib import Path
from email.utils import parsedate_to_datetime

import requests
from pyquery import PyQuery as pq


BASE_URL = os.getenv("TUNASYNC_UPSTREAM_URL", "https://download.docker.com/")
WORKING_DIR = os.getenv("TUNASYNC_WORKING_DIR")


class RemoteSite:

    def __init__(self, base_url=BASE_URL):
        if not base_url.endswith('/'):
            base_url = base_url + '/'
        self.base_url = base_url
        self.meta_urls = []

    def is_metafile_url(self, url):
        deb_dists=('debian', 'ubuntu', 'raspbian')
        rpm_dists=('fedora', 'centos')

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

        r = requests.get(base_url)
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


def curl_download(remote_url: str, dst_file: Path):
    sp.check_call([
        "curl", "-o", str(dst_file),
        "-sL", "--remote-time", "--show-error",
        "--fail", remote_url,
    ])


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--working-dir", default=WORKING_DIR)
    args = parser.parse_args()

    if args.working_dir is None:
        raise Exception("Working Directory is None")

    working_dir = Path(args.working_dir)

    remote_filelist = []
    rs = RemoteSite(args.base_url)
    for url in rs.files:
        dst_file = working_dir / rs.relpath(url)
        remote_filelist.append(dst_file.relative_to(working_dir))

        if dst_file.is_file():
            r = requests.head(url)
            remote_filesize = int(r.headers['content-length'])
            remote_date = parsedate_to_datetime(r.headers['last-modified'])
            stat = dst_file.stat()
            local_filesize = stat.st_size
            local_mtime = stat.st_mtime

            if remote_filesize == local_filesize and remote_date.timestamp() == local_mtime:
                print("Skipping", dst_file.relative_to(working_dir), flush=True)
                continue

            dst_file.unlink()
        else:
            dst_file.parent.mkdir(parents=True, exist_ok=True)

        print("downloading", url, flush=True)
        try:
            curl_download(url, dst_file)
        except Exception:
            print("Failed to download", url, flush=True)
            if dst_file.is_file():
                dst_file.unlink()

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
