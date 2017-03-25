#!/usr/bin/env python3
import json
import re


def version(v: str):
    return tuple(map(int, v.split('.')))


def generate_fileindex(filelist):
    fname_re = re.compile(
        r'''
        (?P<tensorflow>[a-z_]+?)-  # match tensorflow and tensorflow_gpu
        (?P<tfver>[\d.]+?)-        # match version
        (?P<python>[cpy\d]+?)-     # python version, 'rc's are ignored
        (?P<rest>.+?\.whl)         # everything else
        ''',
        re.VERBOSE,
    )

    versions = set([])
    pythons = {
        'linux': set([]),
        'mac': set([]),
        'windows': set([])
    }
    pkglist = []

    min_ver = version('0.10.0')

    for fpath in filelist:
        tokens = fpath.split('/')
        if len(tokens) != 3:
            continue
        os, xpu, fname = tokens
        m = fname_re.match(fname)
        if m is None:
            continue

        if not m.group('tensorflow').startswith('tensorflow'):
            continue

        tfver = m.group('tfver')
        if version(tfver) < min_ver:
            continue
        versions.add(tfver)

        pyver = m.group('python')
        pythons[os].add(pyver)

        pkglist.append({
            'os': os,
            'xpu': xpu,
            'python': pyver,
            'version': tfver,
            'filename': fname,
        })

    pythons = {
        k: sorted(list(v), reverse=True)
        for k, v in pythons.items()
    }
    versions = sorted(list(versions), key=lambda x: version(x), reverse=True)

    index = {
        'versions': versions,
        'pythons': pythons,
        'pkglist': pkglist,
    }

    return index


if __name__ == "__main__":
    import fileinput
    filelist = [line.strip() for line in fileinput.input()]
    index = generate_fileindex(filelist)
    print(json.dumps(index, sort_keys=True, indent=2))


# vim: ts=4 sw=4 sts=4 expandtab
