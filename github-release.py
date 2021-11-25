#!/usr/bin/env python3
import os
import sys
import threading
import traceback
import queue
from pathlib import Path
from datetime import datetime
import tempfile

import requests


BASE_URL = os.getenv("TUNASYNC_UPSTREAM_URL", "https://api.github.com/repos/")
WORKING_DIR = os.getenv("TUNASYNC_WORKING_DIR")
REPOS = [
    "Homebrew/homebrew-portable-ruby",  # Used by homebrew-bottles
    {"repo": "googlefonts/noto-fonts", "tarball": True},
    {"repo": "googlefonts/noto-cjk", "tarball": True},
    {"repo": "googlefonts/noto-emoji", "tarball": True},
    "be5invis/Sarasa-Gothic",
    "be5invis/Iosevka",
    "z4yx/GoAuthing",
    "VSCodium/vscodium",
    "openark/orchestrator",
    "git-lfs/git-lfs",
    "git-for-windows/git",
    "prometheus/prometheus",
    {"repo": "commercialhaskell/stackage-content", "versions": -1},  # Used by stackage
    {"repo": "xxr3376/Learn-Project", "versions": -1},
    {"repo": "robertying/learnX", "versions": -1},
    "rust-analyzer/rust-analyzer",
    "kubernetes/minikube",
    {"repo": "iina/iina", "versions": -1, "pre_release": True, "flat": True},
    {"repo": "FreeCAD/FreeCAD", "versions": 3, "pre_release": True},
    "goharbor/harbor",
    {"repo": "tuna/thuthesis", "versions": -1, "flat": True},
    "cmderdev/cmder",
    "balena-io/etcher",
    "llvm/llvm-project",
    "conda-forge/miniforge",
    "texstudio-org/texstudio",
    "Stellarium/stellarium",
    "UNIDY2002/THUInfo",
    {"repo": "obsproject/obs-studio", "versions": 5, "pre_release": False},
    "com-lihaoyi/mill", # better scala build tool,
    "dbeaver/dbeaver", # issue #1348
]

# connect and read timeout value
TIMEOUT_OPTION = (7, 10)
total_size = 0

def sizeof_fmt(num, suffix='iB'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return "%3.2f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.2f%s%s" % (num, 'Y', suffix)

# wrap around requests.get to use token if available
def github_get(*args, **kwargs):
    headers = kwargs['headers'] if 'headers' in kwargs else {}
    if 'GITHUB_TOKEN' in os.environ:
        headers['Authorization'] = 'token {}'.format(
            os.environ['GITHUB_TOKEN'])
    kwargs['headers'] = headers
    return requests.get(*args, **kwargs)


def do_download(remote_url: str, dst_file: Path, remote_ts: float, remote_size: int):
    # NOTE the stream=True parameter below
    with github_get(remote_url, stream=True) as r:
        r.raise_for_status()
        tmp_dst_file = None
        try:
            with tempfile.NamedTemporaryFile(prefix="." + dst_file.name + ".", suffix=".tmp", dir=dst_file.parent, delete=False) as f:
                tmp_dst_file = Path(f.name)
                for chunk in r.iter_content(chunk_size=1024**2):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        # f.flush()
            # check for downloaded size
            downloaded_size = tmp_dst_file.stat().st_size
            if remote_size != -1 and downloaded_size != remote_size:
                raise Exception(f'File {dst_file.as_posix()} size mismatch: downloaded {downloaded_size} bytes, expected {remote_size} bytes')
            os.utime(tmp_dst_file, (remote_ts, remote_ts))
            tmp_dst_file.chmod(0o644)
            tmp_dst_file.replace(dst_file)
        finally:
            if not tmp_dst_file is None:
                if tmp_dst_file.is_file():
                    tmp_dst_file.unlink()


def downloading_worker(q):
    while True:
        item = q.get()
        if item is None:
            break

        url, dst_file, working_dir, updated, remote_size = item

        print("downloading", url, "to",
              dst_file.relative_to(working_dir), flush=True)
        try:
            do_download(url, dst_file, updated, remote_size)
        except Exception:
            print("Failed to download", url, flush=True)
            if dst_file.is_file():
                dst_file.unlink()

        q.task_done()


def create_workers(n):
    task_queue = queue.Queue()
    for i in range(n):
        t = threading.Thread(target=downloading_worker, args=(task_queue, ))
        t.start()
    return task_queue


def ensure_safe_name(filename):
    filename = filename.replace('\0', ' ')
    if filename == '.':
        return ' .'
    elif filename == '..':
        return '. .'
    else:
        return filename.replace('/', '\\').replace('\\', '_')


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--working-dir", default=WORKING_DIR)
    parser.add_argument("--workers", default=1, type=int,
                        help='number of concurrent downloading jobs')
    parser.add_argument("--fast-skip", action='store_true',
                        help='do not verify size and timestamp of existing files')
    args = parser.parse_args()

    if args.working_dir is None:
        raise Exception("Working Directory is None")

    working_dir = Path(args.working_dir)
    task_queue = create_workers(args.workers)
    remote_filelist = []
    cleaning = False

    def download(release, release_dir, tarball = False):
        global total_size

        if tarball:
            url = release['tarball_url']
            updated = datetime.strptime(
                release['published_at'], '%Y-%m-%dT%H:%M:%SZ').timestamp()
            dst_file = release_dir / 'repo-snapshot.tar.gz'
            remote_filelist.append(dst_file.relative_to(working_dir))

            if dst_file.is_file():
                print("skipping", dst_file.relative_to(working_dir), flush=True)
            else:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                # tarball has no size information, use -1 to skip size check
                task_queue.put((url, dst_file, working_dir, updated, -1))

        for asset in release['assets']:
            url = asset['browser_download_url']
            updated = datetime.strptime(
                asset['updated_at'], '%Y-%m-%dT%H:%M:%SZ').timestamp()
            dst_file = release_dir / ensure_safe_name(asset['name'])
            remote_filelist.append(dst_file.relative_to(working_dir))
            remote_size = asset['size']
            total_size += remote_size

            if dst_file.is_file():
                if args.fast_skip:
                    print("fast skipping", dst_file.relative_to(
                        working_dir), flush=True)
                    continue
                else:
                    stat = dst_file.stat()
                    local_filesize = stat.st_size
                    local_mtime = stat.st_mtime
                    # print(f"{local_filesize} vs {asset['size']}")
                    # print(f"{local_mtime} vs {updated}")
                    if local_mtime > updated or \
                        remote_size == local_filesize and local_mtime == updated:
                        print("skipping", dst_file.relative_to(
                            working_dir), flush=True)
                        continue
            else:
                dst_file.parent.mkdir(parents=True, exist_ok=True)

            task_queue.put((url, dst_file, working_dir, updated, remote_size))

    def link_latest(name, repo_dir):
        try:
            os.unlink(repo_dir / "LatestRelease")
        except OSError:
            pass
        try:
            os.symlink(name, repo_dir / "LatestRelease")
        except OSError:
            pass

    for cfg in REPOS:
        flat = False # build a folder for each release
        versions = 1 # keep only one release
        tarball = False # do not download the tarball
        prerelease = False # filter out pre-releases
        if isinstance(cfg, str):
            repo = cfg
        else:
            repo = cfg["repo"]
            if "versions" in cfg:
                versions = cfg["versions"]
            if "flat" in cfg:
                flat = cfg["flat"]
            if "tarball" in cfg:
                tarball = cfg["tarball"]
            if "pre_release" in cfg:
                prerelease = cfg["pre_release"]

        repo_dir = working_dir / Path(repo)
        print(f"syncing {repo} to {repo_dir}")

        try:
            r = github_get(f"{args.base_url}{repo}/releases")
            r.raise_for_status()
            releases = r.json()
        except:
            traceback.print_exc()
            break

        n_downloaded = 0
        for release in releases:
            if not release['draft'] and (prerelease or not release['prerelease']):
                name = ensure_safe_name(release['name'] or release['tag_name'])
                if len(name) == 0:
                    print("Error: Unnamed release")
                    continue
                download(release, (repo_dir if flat else repo_dir / name), tarball)
                if n_downloaded == 0 and not flat:
                    # create a symbolic link to the latest release folder
                    link_latest(name, repo_dir)
                n_downloaded += 1
                if versions > 0 and n_downloaded >= versions:
                    break
        if n_downloaded == 0:
            print(f"Error: No release version found for {repo}")
            continue
    else:
        cleaning = True

    # block until all tasks are done
    task_queue.join()
    # stop workers
    for i in range(args.workers):
        task_queue.put(None)

    if cleaning:
        local_filelist = []
        for local_file in working_dir.glob('**/*'):
            if local_file.is_file():
                local_filelist.append(local_file.relative_to(working_dir))

        for old_file in set(local_filelist) - set(remote_filelist):
            print("deleting", old_file, flush=True)
            old_file = working_dir / old_file
            old_file.unlink()

        for local_dir in working_dir.glob('*/*/*'):
            if local_dir.is_dir():
                try:
                    # remove empty dirs only
                    local_dir.rmdir()
                except:
                    pass

        print("Total size is", sizeof_fmt(total_size, suffix=""))

if __name__ == "__main__":
    main()


# vim: ts=4 sw=4 sts=4 expandtab
