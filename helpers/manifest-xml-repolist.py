#!/usr/bin/env python3
import argparse
import xml.etree.ElementTree as ET


def get_repolist(manifest_file: str, remotes: list):
    manifest = ET.parse(manifest_file)
    default_remote = None
    default = manifest.find('default')
    if default is not None:
        default_remote = default.get('remote')
    for project in manifest.findall('project'):
        if project.get('remote', default=default_remote) in remotes:
            yield(project)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest",
                        help='path to manifest.xml')
    parser.add_argument("remote", nargs='+',
                        help='remotes whose projects should be included')
    args = parser.parse_args()
    present = set()
    for repo in get_repolist(args.manifest, args.remote):
        name = repo.get('name')
        if name not in present:
            print(name)
            present.add(name)


if __name__ == "__main__":
    main()

# vim: ts=4 sw=4 sts=4 expandtab
