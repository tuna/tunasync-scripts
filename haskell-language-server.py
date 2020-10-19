#!/usr/bin/env python3

# python deps: requests
# non-python deps: aria2

import os
import requests
import pathlib
import json
import subprocess
import shutil

_base_path = pathlib.Path(os.environ['TUNASYNC_WORKING_DIR'])


def download(dir_, url, force=False):
    dir_path = _base_path / dir_
    file_path = dir_path / url.split('/')[-1]
    if force and file_path.is_file():
        file_path.unlink()
    if file_path.is_file():
        print('{} exists, skipping'.format(file_path), flush=True)
    else:
        args = [
            'aria2c', url, '--dir={}'.format(
                dir_path), '--out={}.tmp'.format(url.split('/')[-1]),
            '--file-allocation=none', '--quiet=true'
        ]
        subprocess.run(args, check=True)
        shutil.move('{}.tmp'.format(file_path), file_path)
        print('Downloaded {} to {}'.format(url, file_path), flush=True)


releasesInfo = requests.get(
    'https://api.github.com/repos/haskell/haskell-language-server/releases').content

g = json.loads(releasesInfo)

# download latest assets and modify json
# download to _base_path/version_name/file_name
for i in range(0, len(g[0]['assets'])-1):
    print("Start Download:", g[0]['assets'][i]['browser_download_url'])

    download(g[0]['name'], g[0]['assets'][i]['browser_download_url'])

    g[0]['assets'][i]['browser_download_url'] = (
        g[0]['assets'][i]['browser_download_url'].replace(
            'https://github.com/haskell/haskell-language-server/releases/download',
            'https://mirrors.tuna.tsinghua.edu.cn/haskell-language-server'
            # _base_path.as_posix()
        )
    )

# dump json onto the _base_path
with open(_base_path / 'releasesInfo.json', 'w') as releasesInfoFile:
    json.dump(g, releasesInfoFile, indent=4)
