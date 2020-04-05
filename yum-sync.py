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
from typing import List, Dict
import requests

def check_args(prop: str, lst: List[str]):
    for s in lst:
        if len(s)==0 or ' ' in s:
            raise ValueError(f"Invalid item in {prop}: {repr(s)}")

def substitute_vars(s: str, vardict: Dict[str, str]) -> str:
    for key, val in vardict.items():
        tpl = "@{"+key+"}"
        s = s.replace(tpl, val)
    return s

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", type=str, help="base URL")
    parser.add_argument("os_version", type=str, help="e.g. 6-8")
    parser.add_argument("component", type=str, help="e.g. mysql56-community,mysql57-community")
    parser.add_argument("arch", type=str, help="e.g. x86_64")
    parser.add_argument("repo_name", type=str, help="e.g. @{comp}-el@{os_ver}}")
    parser.add_argument("working_dir", type=Path, help="working directory")
    args = parser.parse_args()

    if '-' in args.os_version:
        dash = args.os_version.index('-')
        os_list = [ str(i) for i in range(
            int(args.os_version[:dash]),
            1+int(args.os_version[dash+1:])) ]
    else:
        os_list = [args.os_version]
    check_args("os_version", os_list)
    component_list = args.component.split(',')
    check_args("component", component_list)
    arch_list = args.arch.split(',')
    check_args("arch", arch_list)

    failed = []
    args.working_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = tempfile.mkdtemp()

    def combination_os_comp(arch: str):
        for os in os_list:
            for comp in component_list:
                vardict = {
                    'arch': arch,
                    'os_ver': os,
                    'comp': comp,
                }

                name = substitute_vars(args.repo_name, vardict)
                url = substitute_vars(args.base_url, vardict)
                try:
                    r = requests.head((url+"/repodata/repomd.xml").replace("//", "/"), timeout=(7,7))
                    if r.status_code < 400 or r.status_code == 403:
                        yield (name, url)
                    else:
                        print(url, "->", r.status_code)
                except:
                    traceback.print_exc()

    for arch in arch_list:
        dest_dirs = []
        conf = tempfile.NamedTemporaryFile("w", suffix=".conf")
        conf.write('''
[main]
keepcache=0
''')
        for name, url in combination_os_comp(arch):
            conf.write(f'''
[{name}]
name={name}
baseurl={url}
repo_gpgcheck=0
gpgcheck=0
enabled=1
''')
            dest_dirs.append((args.working_dir / name).absolute())
        conf.flush()
        sp.run(["cat", conf.name])
        # sp.run(["ls", "-la", cache_dir])

        if len(dest_dirs) == 0:
            print("Nothing to sync")
            failed.append(('', arch))
            continue

        cmd_args = ["reposync", "-a", arch, "-c", conf.name, "-d", "-p", str(args.working_dir.absolute()), "-e", cache_dir]
        # print(cmd_args)
        ret = sp.run(cmd_args)
        if ret.returncode != 0:
            failed.append((name, arch))
            continue

        for path in dest_dirs:
            path.mkdir(exist_ok=True)
            cmd_args = ["createrepo", "--update", "-v", "-c", cache_dir, "-o", str(path), str(path)]
            # print(cmd_args)
            ret = sp.run(cmd_args)

    if len(failed) > 0:
        print("Failed YUM repos: ", failed)

if __name__ == "__main__":
    main()
