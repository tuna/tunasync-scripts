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
from typing import List, Tuple, IO

import requests

OS_TEMPLATE = {
    'ubuntu-current': ["trusty", "xenial", "bionic", "eoan"],
    'ubuntu-lts': ["trusty", "xenial", "bionic"],
    'debian-current': ["jessie", "stretch", "buster"],
}
MAX_RETRY=int(os.getenv('MAX_RETRY', '3'))
DOWNLOAD_TIMEOUT=int(os.getenv('DOWNLOAD_TIMEOUT', '1800'))

pattern_os_template = re.compile(r"@\{(.+)\}")
pattern_package_name = re.compile(r"^Filename: (.+)$", re.MULTILINE)
pattern_package_size = re.compile(r"^Size: (\d+)$", re.MULTILINE)
pattern_package_sha256 = re.compile(r"^SHA256: (\w{64})$", re.MULTILINE)

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

def check_and_download(url: str, dst_file: Path)->int:
    try:
        start = time.time()
        with requests.get(url, stream=True, timeout=(5, 10)) as r:
            r.raise_for_status()
            if 'last-modified' in r.headers:
                remote_ts = parsedate_to_datetime(
                    r.headers['last-modified']).timestamp()
            else: remote_ts = None

            with dst_file.open('wb') as f:
                for chunk in r.iter_content(chunk_size=1024**2):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                    if time.time() - start > DOWNLOAD_TIMEOUT:
                        raise TimeoutError("Download timeout")
            if remote_ts is not None:
                os.utime(dst_file, (remote_ts, remote_ts))
        return 0
    except BaseException as e:
        print(e)
        if dst_file.is_file():
            dst_file.unlink()
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
        file.rename(dst / file.name) # Overwrite files
    if empty:
        print(f"{src} is empty")

def apt_mirror(base_url: str, dist: str, repo: str, arch: str, dest_base_dir: Path, filelist: IO[str])->int:
    if not dest_base_dir.is_dir():
        print("Destination directory is empty, cannot continue")
        return 1
    print(f"Started mirroring {base_url} {dist}, {repo}, {arch}!")

	# download Release files
    dist_dir,dist_tmp_dir = mkdir_with_dot_tmp(dest_base_dir / "dists" / dist)
    check_and_download(f"{base_url}/dists/{dist}/Contents-{arch}.gz",dist_tmp_dir / f"Contents-{arch}.gz")
    check_and_download(f"{base_url}/dists/{dist}/InRelease",dist_tmp_dir / "InRelease")
    if check_and_download(f"{base_url}/dists/{dist}/Release",dist_tmp_dir / "Release") != 0:
        print("Invalid Repository")
        return 1
    check_and_download(f"{base_url}/dists/{dist}/Release.gpg",dist_tmp_dir / "Release.gpg")

	# download Contents files
    comp_dir,comp_tmp_dir = mkdir_with_dot_tmp(dist_dir / repo)
    check_and_download(f"{base_url}/dists/{dist}/{repo}/Contents-{arch}", comp_tmp_dir/f"Contents-{arch}")
    check_and_download(f"{base_url}/dists/{dist}/{repo}/Contents-{arch}.gz", comp_tmp_dir/f"Contents-{arch}.gz")
    check_and_download(f"{base_url}/dists/{dist}/{repo}/Contents-{arch}.bz2", comp_tmp_dir/f"Contents-{arch}.bz2")

	# load Package Index URLs from the Release file
    release_file = dist_tmp_dir / "Release"
    pkgidx_dir,pkgidx_tmp_dir = mkdir_with_dot_tmp(comp_dir / f"binary-{arch}")
    with open(release_file, "r") as fd:
        pkgidx_content=None
        cnt_start=False
        for line in fd:
            if cnt_start:
                fields = line.split()
                if len(fields) != 3 or len(fields[0]) != 64: # 64 is SHA-256 checksum length
                    break
                checksum, filesize, filename = tuple(fields)
                if filename.startswith(f"{repo}/binary-{arch}"):
                    pkgidx_filename = Path(filename).name # base name
                    pkgidx_file = pkgidx_tmp_dir / pkgidx_filename
                    pkglist_url = f"{base_url}/dists/{dist}/{filename}"
                    if check_and_download(pkglist_url, pkgidx_file) != 0:
                        print("Failed to download:", pkglist_url)
                        continue
                    
                    with pkgidx_file.open('rb') as t: content = t.read()
                    if len(content) != int(filesize):
                        print(f"Invalid size of {pkgidx_file}, expected {filesize}")
                        return 1
                    if hashlib.sha256(content).hexdigest() != checksum:
                        print(f"Invalid checksum of {pkgidx_file}, expected {checksum}")
                        return 1
                    if pkgidx_content is None:
                        print("getting packages index content")
                        suffix = pkgidx_file.suffix
                        if suffix == '.xz':
                            pkgidx_content = lzma.decompress(content).decode('utf-8')
                        elif suffix == '.bz2':
                            pkgidx_content = bz2.decompress(content).decode('utf-8')
                        elif suffix == '.gz':
                            pkgidx_content = gzip.decompress(content).decode('utf-8')
                        elif suffix == '':
                            pkgidx_content = content.decode('utf-8')

            # Currently only support SHA-256 checksum, because
            # "Clients may not use the MD5Sum and SHA1 fields for security purposes, and must require a SHA256 or a SHA512 field."
            # from https://wiki.debian.org/DebianRepository/Format#A.22Release.22_files
            if line.startswith('SHA256:'):
                cnt_start = True
    if not cnt_start:
        print("Cannot find SHA-256 checksum")
        return 1
    if pkgidx_content is None:
        print("index is empty, failed")
        return 1

    # Download packages
    err = 0
    deb_count = 0
    for pkg in pkgidx_content.split('\n\n'):
        if len(pkg) < 10: # ignore blanks
            continue
        try:
            pkg_filename = pattern_package_name.search(pkg).group(1)
            pkg_size = int(pattern_package_size.search(pkg).group(1))
            pkg_checksum = pattern_package_sha256.search(pkg).group(1)
        except:
            print("Failed to parse one package description")
            traceback.print_exc()
            err = 1
            continue
        
        filelist.write(pkg_filename + '\n')
        dest_filename = dest_base_dir / pkg_filename
        dest_dir = dest_filename.parent
        if not dest_dir.is_dir():
            dest_dir.mkdir(parents=True, exist_ok=True)
        if dest_filename.is_file() and dest_filename.stat().st_size == pkg_size:
            print(f"Skipping {pkg_filename}, size {pkg_size}")
            continue

        pkg_url=f"{base_url}/{pkg_filename}"
        for retry in range(MAX_RETRY):
            print(f"downloading {pkg_url} to {dest_filename}")
            if check_and_download(pkg_url, dest_filename) != 0:
                continue

            sha = hashlib.sha256()
            with dest_filename.open("rb") as f:
                for block in iter(lambda: f.read(1024**2), b""):
                    sha.update(block)
            if sha.hexdigest() != pkg_checksum:
                print(f"Invalid checksum of {dest_filename}, expected {pkg_checksum}")
                dest_filename.unlink()
                continue
            break
        else:
            print(f"Failed to download {dest_filename}")
            err = 1
        deb_count += 1
        # if deb_count == 2:
        #     break
    try:
        move_files_in(pkgidx_tmp_dir, pkgidx_dir)
        move_files_in(comp_tmp_dir, comp_dir)
        move_files_in(dist_tmp_dir, dist_dir)

        shutil.rmtree(str(pkgidx_tmp_dir))
        shutil.rmtree(str(comp_tmp_dir))
        shutil.rmtree(str(dist_tmp_dir))
    except:
        traceback.print_exc()
        return 1

    print(f"Mirroring {base_url} {dist}, {repo}, {arch} done!")
    return err

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", type=str, help="base URL")
    parser.add_argument("os_version", type=str, help="e.g. buster,@ubuntu-lts")
    parser.add_argument("component", type=str, help="e.g. multiverse,contrib")
    parser.add_argument("arch", type=str, help="e.g. i386,amd64")
    parser.add_argument("working_dir", type=Path, help="working directory")
    parser.add_argument("--delete", action='store_true',
                        help='delete unreferenced package files')
    args = parser.parse_args()

    os_list = args.os_version.split(',')
    check_args("os_version", os_list)
    component_list = args.component.split(',')
    check_args("component", component_list)
    arch_list = args.arch.split(',')
    check_args("arch", arch_list)

    os_list = replace_os_template(os_list)

    args.working_dir.mkdir(parents=True, exist_ok=True)
    filelist = tempfile.mkstemp()
    failed = []

    # apt_download = Path(__file__).parent / "helpers" / "apt-download-binary"
    # if not apt_download.is_file():
    #     raise OSError(f"File not found: {apt_download}")

    for os in os_list:
        for comp in component_list:
            for arch in arch_list:
                # shell_args = [
                #     str(apt_download.absolute()),
                #     args.base_url,
                #     os, comp, arch,
                #     str(args.working_dir.absolute()),
                #     filelist[1] ]
                # # print(shell_args)
                # ret = sp.run(shell_args)
                # if ret.returncode != 0:
                #     failed.append((os, comp, arch))
                with open(filelist[1], "w") as pkg_file_list:
                    if apt_mirror(args.base_url, os, comp, arch, args.working_dir, pkg_file_list) != 0:
                        failed.append((os, comp, arch))
    if len(failed) > 0:
        print(f"Failed APT repos of {args.base_url}: ", failed)
    if args.delete:
        pass #TODO

if __name__ == "__main__":
    main()
