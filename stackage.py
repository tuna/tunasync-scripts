#!/usr/bin/env python3

# python deps: requests, pyyaml
# non-python deps: aria2, git

import os
import pathlib
import requests
import shutil
import subprocess
import yaml


class StackageSession(object):
    def __init__(self):
        self._base_path = pathlib.Path(os.environ['TUNASYNC_WORKING_DIR'])

    def download(self, dir_, url, sha1=None, force=False):
        dir_path = self._base_path / dir_
        file_path = dir_path / url.split('/')[-1]
        if force and file_path.is_file():
            file_path.unlink()
        if file_path.is_file():
            print('{} exists, skipping'.format(file_path), flush=True)
        else:
            args = [
                'aria2c', url, '--dir={}'.format(dir_path), '--out={}.tmp'.format(url.split('/')[-1]),
                '--file-allocation=none', '--quiet=true'
            ]
            if sha1:
                args.append('--checksum=sha-1={}'.format(sha1))
            subprocess.run(args, check=True)
            shutil.move('{}.tmp'.format(file_path), file_path)
            print('Downloaded {} to {}'.format(url, file_path), flush=True)

    def load_stack_setup(self):
        d = yaml.load(
            requests
                .get('https://raw.githubusercontent.com/fpco/stackage-content/master/stack/stack-setup-2.yaml')
                .content
        )
        for platform in d['ghc']:
            for ver in d['ghc'][platform]:
                self.download(
                    'ghc',
                    d['ghc'][platform][ver]['url'],
                    d['ghc'][platform][ver]['sha1'],
                )
                d['ghc'][platform][ver]['url'] = (
                    'http://mirrors.tuna.tsinghua.edu.cn/stackage/ghc/{}'
                        .format(d['ghc'][platform][ver]['url'].split('/')[-1])
                )

        d['msys2'] = {
            'windows32': {
                'version': '20161025',
                'url': 'http://mirrors.tuna.tsinghua.edu.cn/msys2/distrib/i686/msys2-base-i686-20161025.tar.xz',
                'content-length': 47526500,
                'sha1': '5d17fa53077a93a38a9ac0acb8a03bf6c2fc32ad',
            },
            'windows64': {
                'version': '20161025',
                'url': 'http://mirrors.tuna.tsinghua.edu.cn/msys2/distrib/x86_64/msys2-base-x86_64-20161025.tar.xz',
                'content-length': 47166584,
                'sha1': '05fd74a6c61923837dffe22601c9014f422b5460',
            }
        }
        for i in ['portable-git', 'stack', 'ghcjs']:
            del d[i]
        with open(self._base_path / 'stack-setup.yaml', 'w') as f:
            yaml.dump(d, f)
        print('Loaded stack-setup.yaml', flush=True)

    def load_stackage_snapshots(self):
        for channel in ['lts-haskell', 'stackage-nightly']:
            if (self._base_path / channel).is_dir():
                args = ['git', '-C', self._base_path / channel, 'pull']
            else:
                args = ['git', '-C', self._base_path, 'clone', '--depth', '1',
                        'https://github.com/fpco/{}.git'.format(channel)]
            subprocess.run(args, check=True)
            print('Loaded {}'.format(channel), flush=True)

        self.download(
            '',
            'https://www.stackage.org/download/snapshots.json',
            force=True,
        )
        print('Loaded snapshots.json', flush=True)


if __name__ == '__main__':
    s = StackageSession()
    s.load_stackage_snapshots()
    s.load_stack_setup()
