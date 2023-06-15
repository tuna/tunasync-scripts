#!/usr/bin/env python3
import hashlib
import traceback
import json
import os
import re
import shutil
import subprocess as sp
import tempfile
import argparse
import bz2
import gzip
import lzma
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import List, Dict, Set, Tuple, IO

import requests


APT_SYNC_USER_AGENT = os.getenv("APT_SYNC_USER_AGENT", "APT-Mirror-Tool/1.0")
requests.utils.default_user_agent = lambda: APT_SYNC_USER_AGENT

OS_TEMPLATE = {
    'ubuntu-lts': ["bionic", "focal", "jammy"],
    'debian-current': ["buster", "bullseye", "bookworm"],
    'debian-latest2': ["bullseye", "bookworm"],
    'debian-latest': ["bookworm"],
}
ARCH_NO_PKGIDX = ['dep11', 'i18n', 'cnf']
MAX_RETRY=int(os.getenv('MAX_RETRY', '3'))
DOWNLOAD_TIMEOUT=int(os.getenv('DOWNLOAD_TIMEOUT', '1800'))
REPO_SIZE_FILE = os.getenv('REPO_SIZE_FILE', '')

pattern_os_template = re.compile(r"@\{(.+)\}")
pattern_package_name = re.compile(r"^Filename: (.+)$", re.MULTILINE)
pattern_package_size = re.compile(r"^Size: (\d+)$", re.MULTILINE)
pattern_package_sha256 = re.compile(r"^SHA256: (\w{64})$", re.MULTILINE)
download_cache = dict()

def check_args(prop: str, lst: List[str]):
    for s in lst:
        if len(s)==0 or ' ' in s:
            raise ValueError(f"Invalid item in {prop}: {repr(s)}")

def replace_os_template(os_list: List[str]) -> List[str]:
    ret = []
    for i in os_list:
        matched = pattern_os_template.search(i)
        if matched:
            for os in OS_TEMPLATE[matched.group(1)]:
                ret.append(pattern_os_template.sub(os, i))
        elif i.startswith('@'):
            ret.extend(OS_TEMPLATE[i[1:]])
        else:
            ret.append(i)
    return ret

def check_and_download(url: str, dst_file: Path, caching = False)->int:
    try:
        if caching:
            if url in download_cache:
                print(f"Using cached content: {url}", flush=True)
                with dst_file.open('wb') as f:
                    f.write(download_cache[url])
                return 0
            download_cache[url] = bytes()
        start = time.time()
        with requests.get(url, stream=True, timeout=(5, 10)) as r:
            r.raise_for_status()
            if 'last-modified' in r.headers:
                remote_ts = parsedate_to_datetime(
                    r.headers['last-modified']).timestamp()
            else: remote_ts = None

            with dst_file.open('wb') as f:
                for chunk in r.iter_content(chunk_size=1024**2):
                    if time.time() - start > DOWNLOAD_TIMEOUT:
                        raise TimeoutError("Download timeout")
                    if not chunk: continue # filter out keep-alive new chunks

                    f.write(chunk)
                    if caching: download_cache[url] += chunk
            if remote_ts is not None:
                os.utime(dst_file, (remote_ts, remote_ts))
        return 0
    except BaseException as e:
        print(e, flush=True)
        if dst_file.is_file(): dst_file.unlink()
        if url in download_cache: del download_cache[url]
    return 1

def mkdir_with_dot_tmp(folder: Path)->Tuple[Path, Path]:
    tmpdir = folder / ".tmp"
    if tmpdir.is_dir():
        shutil.rmtree(str(tmpdir))
    tmpdir.mkdir(parents=True, exist_ok=True)
    return (folder, tmpdir)

def move_files_in(src: Path, dst: Path):
    empty = True
    for file in src.glob('*'):
        empty = False
        print(f"moving {file} to {dst}")
        # shutil.move(str(file), str(dst))
        if file.is_dir():
            (dst / file.name).mkdir(parents=True, exist_ok=True)
            move_files_in(file, dst / file.name)
            file.rmdir() # rmdir wont fail as all files in it have been moved
        else:
            file.rename(dst / file.name) # Overwrite files
    if empty:
        print(f"{src} is empty")

def apt_mirror(base_url: str, dist: str, repo: str, arch: str, dest_base_dir: Path, deb_set: Dict[str, int])->int:
    if not dest_base_dir.is_dir():
        print("Destination directory is empty, cannot continue")
        return 1
    print(f"Started mirroring {base_url} {dist}, {repo}, {arch}!", flush=True)

	# download Release files
    dist_dir,dist_tmp_dir = mkdir_with_dot_tmp(dest_base_dir / "dists" / dist)
    check_and_download(f"{base_url}/dists/{dist}/InRelease",dist_tmp_dir / "InRelease", caching=True)
    if check_and_download(f"{base_url}/dists/{dist}/Release",dist_tmp_dir / "Release", caching=True) != 0:
        print("Invalid Repository")
        if not (dist_dir/"Release").is_file():
            print(f"{dist_dir/'Release'} never existed, upstream may not provide packages for {dist}, ignore this error")
            return 0
        return 1
    check_and_download(f"{base_url}/dists/{dist}/Release.gpg",dist_tmp_dir / "Release.gpg", caching=True)

    comp_dir,comp_tmp_dir = mkdir_with_dot_tmp(dist_dir / repo)

	# load Package Index URLs from the Release file
    release_file = dist_tmp_dir / "Release"
    arch_dir = arch if arch in ARCH_NO_PKGIDX else f"binary-{arch}"
    pkgidx_dir,pkgidx_tmp_dir = mkdir_with_dot_tmp(comp_dir / arch_dir)
    with open(release_file, "r") as fd:
        pkgidx_content=None
        cnt_start=False
        for line in fd:
            if cnt_start:
                fields = line.split()
                if len(fields) != 3 or len(fields[0]) != 64: # 64 is SHA-256 checksum length
                    break
                checksum, filesize, filename = tuple(fields)
                if filename.startswith(f"{repo}/{arch_dir}/") or \
                   filename.startswith(f"{repo}/Contents-{arch}") or \
                   filename.startswith(f"Contents-{arch}"):
                    fn = Path(filename)
                    if len(fn.parts) <= 3:
                        # Contents-amd64.gz
                        # main/Contents-amd64.gz
                        # main/binary-all/Packages
                        pkgidx_file = dist_dir / fn.parent / ".tmp" / fn.name
                    else:
                        # main/dep11/by-hash/MD5Sum/0af5c69679a24671cfd7579095a9cb5e
                        # deep_tmp_dir is in pkgidx_tmp_dir hence no extra garbage collection needed
                        deep_tmp_dir = dist_dir / Path(fn.parts[0]) / Path(fn.parts[1]) / ".tmp" / Path('/'.join(fn.parts[2:-1]))
                        deep_tmp_dir.mkdir(parents=True, exist_ok=True)
                        pkgidx_file = deep_tmp_dir / fn.name
                else:
                    print(f"Ignore the file {filename}")
                    continue
                pkglist_url = f"{base_url}/dists/{dist}/{filename}"
                if check_and_download(pkglist_url, pkgidx_file) != 0:
                    print("Failed to download:", pkglist_url)
                    continue

                with pkgidx_file.open('rb') as t: content = t.read()
                if len(content) != int(filesize):
                    print(f"Invalid size of {pkgidx_file}, expected {filesize}, skipped")
                    pkgidx_file.unlink()
                    continue
                if hashlib.sha256(content).hexdigest() != checksum:
                    print(f"Invalid checksum of {pkgidx_file}, expected {checksum}, skipped")
                    pkgidx_file.unlink()
                    continue
                if pkgidx_content is None and pkgidx_file.stem == 'Packages':
                    print(f"getting packages index content from {pkgidx_file.name}", flush=True)
                    suffix = pkgidx_file.suffix
                    if suffix == '.xz':
                        pkgidx_content = lzma.decompress(content).decode('utf-8')
                    elif suffix == '.bz2':
                        pkgidx_content = bz2.decompress(content).decode('utf-8')
                    elif suffix == '.gz':
                        pkgidx_content = gzip.decompress(content).decode('utf-8')
                    elif suffix == '':
                        pkgidx_content = content.decode('utf-8')
                    else:
                        print("unsupported format")

            # Currently only support SHA-256 checksum, because
            # "Clients may not use the MD5Sum and SHA1 fields for security purposes, and must require a SHA256 or a SHA512 field."
            # from https://wiki.debian.org/DebianRepository/Format#A.22Release.22_files
            if line.startswith('SHA256:'):
                cnt_start = True
    if not cnt_start:
        print("Cannot find SHA-256 checksum")
        return 1

    def collect_tmp_dir():
        try:
            move_files_in(pkgidx_tmp_dir, pkgidx_dir)
            move_files_in(comp_tmp_dir, comp_dir)
            move_files_in(dist_tmp_dir, dist_dir)

            pkgidx_tmp_dir.rmdir()
            comp_tmp_dir.rmdir()
            dist_tmp_dir.rmdir()
            return 0
        except:
            traceback.print_exc()
            return 1
    if arch in ARCH_NO_PKGIDX:
        if collect_tmp_dir() == 1:
            return 1
        print(f"Mirroring {base_url} {dist}, {repo}, {arch} done!")
        return 0

    if pkgidx_content is None:
        print("index is empty, failed")
        if len(list(pkgidx_dir.glob('Packages*'))) == 0:
            print(f"{pkgidx_dir/'Packages'} never existed, upstream may not provide {dist}/{repo}/{arch}, ignore this error")
            return 0
        return 1

    # Download packages
    err = 0
    deb_count = 0
    deb_size = 0
    for pkg in pkgidx_content.split('\n\n'):
        if len(pkg) < 10: # ignore blanks
            continue
        try:
            pkg_filename = pattern_package_name.search(pkg).group(1)
            pkg_size = int(pattern_package_size.search(pkg).group(1))
            pkg_checksum = pattern_package_sha256.search(pkg).group(1)
        except:
            print("Failed to parse one package description", flush=True)
            traceback.print_exc()
            err = 1
            continue
        deb_count += 1
        deb_size += pkg_size

        dest_filename = dest_base_dir / pkg_filename
        dest_dir = dest_filename.parent
        if not dest_dir.is_dir():
            dest_dir.mkdir(parents=True, exist_ok=True)
        if dest_filename.suffix == '.deb':
            deb_set[str(dest_filename.relative_to(dest_base_dir))] = pkg_size
        if dest_filename.is_file() and dest_filename.stat().st_size == pkg_size:
            print(f"Skipping {pkg_filename}, size {pkg_size}")
            continue

        pkg_url=f"{base_url}/{pkg_filename}"
        dest_tmp_filename = dest_filename.with_name('._syncing_.' + dest_filename.name)
        for retry in range(MAX_RETRY):
            print(f"downloading {pkg_url} to {dest_filename}", flush=True)
            # break # dry run
            if check_and_download(pkg_url, dest_tmp_filename) != 0:
                continue

            sha = hashlib.sha256()
            with dest_tmp_filename.open("rb") as f:
                for block in iter(lambda: f.read(1024**2), b""):
                    sha.update(block)
            if sha.hexdigest() != pkg_checksum:
                print(f"Invalid checksum of {dest_filename}, expected {pkg_checksum}")
                dest_tmp_filename.unlink()
                continue
            dest_tmp_filename.rename(dest_filename)
            break
        else:
            print(f"Failed to download {dest_filename}")
            err = 1

    if collect_tmp_dir() == 1:
        return 1
    print(f"Mirroring {base_url} {dist}, {repo}, {arch} done!")
    print(f"{deb_count} packages, {deb_size} bytes in total", flush=True)
    return err

def apt_delete_old_debs(dest_base_dir: Path, remote_set: Dict[str, int], dry_run: bool):
    on_disk = set([
        str(i.relative_to(dest_base_dir)) for i in dest_base_dir.glob('**/*.deb')])
    deleting = on_disk - remote_set.keys()
    # print(on_disk)
    # print(remote_set)
    print(f"Deleting {len(deleting)} packages not in the index{' (dry run)' if dry_run else ''}", flush=True)
    for i in deleting:
        if dry_run:
            print("Will delete", i)
        else:
            print("Deleting", i)
            (dest_base_dir/i).unlink()

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", type=str, help="base URL")
    parser.add_argument("os_version", type=str, help="e.g. buster,@ubuntu-lts")
    parser.add_argument("component", type=str, help="e.g. multiverse,contrib")
    parser.add_argument("arch", type=str, help="e.g. i386,amd64")
    parser.add_argument("working_dir", type=Path, help="working directory")
    parser.add_argument("--delete", action='store_true',
                        help='delete unreferenced package files')
    parser.add_argument("--delete-dry-run", action='store_true',
                        help='print package files to be deleted only')
    args = parser.parse_args()

    os_list = args.os_version.split(',')
    check_args("os_version", os_list)
    component_list = args.component.split(',')
    check_args("component", component_list)
    arch_list = args.arch.split(',')
    check_args("arch", arch_list)

    os_list = replace_os_template(os_list)

    args.working_dir.mkdir(parents=True, exist_ok=True)
    failed = []
    deb_set = {}

    for os in os_list:
        for comp in component_list:
            for arch in arch_list:
                if apt_mirror(args.base_url, os, comp, arch, args.working_dir, deb_set=deb_set) != 0:
                    failed.append((os, comp, arch))
    if len(failed) > 0:
        print(f"Failed APT repos of {args.base_url}: ", failed)
        return
    if args.delete or args.delete_dry_run:
        apt_delete_old_debs(args.working_dir, deb_set, args.delete_dry_run)

    if len(REPO_SIZE_FILE) > 0:
        with open(REPO_SIZE_FILE, "a") as fd:
            total_size = sum(deb_set.values())
            fd.write(f"+{total_size}")

if __name__ == "__main__":
    main()
