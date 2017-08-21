#!/usr/bin/env python3
import requests
from pyquery import PyQuery as pq

meta_urls = []


def is_metafile_url(url):
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


def recursive_get_filelist(base_url, filter_meta=False):
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
        if filter_meta and is_metafile_url(href):
            meta_urls.append(href)
        elif link.text.endswith('/'):
            yield from recursive_get_filelist(href, filter_meta=filter_meta)
        else:
            yield href


def get_filelist(base_url):
    yield from recursive_get_filelist(base_url, filter_meta=True)


def get_meta_filelist():
    for url in meta_urls:
        yield from recursive_get_filelist(url, filter_meta=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", default="https://download.docker.com/")
    args = parser.parse_args()

    for file_url in get_filelist(args.base_url):
        print(file_url, flush=True)

    for file_url in get_meta_filelist():
        print(file_url, flush=True)


# vim: ts=4 sw=4 sts=4 expandtab
