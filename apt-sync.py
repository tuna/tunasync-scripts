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
from pathlib import Path
from typing import List

OS_TEMPLATE = {
    'ubuntu-current': ["trusty", "xenial", "bionic", "eoan"],
    'ubuntu-lts': ["trusty", "xenial", "bionic"],
    'debian-current': ["jessie", "stretch", "buster"],
}

pattern_os_template = re.compile(r"@\{(.+)\}")

apt_download = Path(__file__).parent / "helpers" / "apt-download-binary"
if not apt_download.is_file():
    raise OSError(f"File not found: {apt_download}")

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

    for os in os_list:
        for comp in component_list:
            for arch in arch_list:
                shell_args = [
                    str(apt_download.absolute()),
                    args.base_url,
                    os, comp, arch,
                    str(args.working_dir.absolute()),
                    filelist[1] ]
                # print(shell_args)
                ret = sp.run(shell_args)
                if ret.returncode != 0:
                    failed.append((os, comp, arch))
    if len(failed) > 0:
        print(f"Failed APT repos of {args.base_url}: ", failed)
    if args.delete:
        pass #TODO

if __name__ == "__main__":
    main()
