#!/usr/bin/env python3
import argparse
import bz2
import gzip
import logging
import os
import re
import shutil
import sqlite3
import subprocess as sp
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List

import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s.%(msecs)03d - %(filename)s:%(lineno)d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
handler.setFormatter(formatter)
logger.addHandler(handler)

REPO_SIZE_FILE = os.getenv("REPO_SIZE_FILE", "")
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "1800"))
REPO_STAT = {}


OS_TEMPLATE = {
    "rhel-current": ["9", "10"],
    "fedora-current": ["41", "42"],
}

pattern_os_template = re.compile(r"@\{(.+)\}")

def replace_os_template(os_list: List[str]) -> List[str]:
    ret = []
    for i in os_list:
        matched = pattern_os_template.search(i)
        if matched:
            for os in OS_TEMPLATE[matched.group(1)]:
                ret.append(pattern_os_template.sub(os, i))
        elif i.startswith("@"):
            ret.extend(OS_TEMPLATE[i[1:]])
        else:
            ret.append(i)
    return ret

def calc_repo_size(path: Path):
    dbfiles = path.glob("repodata/*primary.*")
    with tempfile.NamedTemporaryFile() as tmp:
        dec = None
        dbfile = None
        for db in dbfiles:
            dbfile = db
            suffixes = db.suffixes
            if suffixes[-1] == ".bz2":
                dec = bz2.decompress
                suffixes = suffixes[:-1]
            elif suffixes[-1] == ".gz":
                dec = gzip.decompress
                suffixes = suffixes[:-1]
            elif suffixes[-1] in (".sqlite", ".xml"):
                dec = lambda x: x
        if dec is None:
            logger.error(f"Failed to read from {path}: {list(dbfiles)}")
            return
        with db.open("rb") as f:
            tmp.write(dec(f.read()))
            tmp.flush()

        if suffixes[-1] == ".sqlite":
            conn = sqlite3.connect(tmp.name)
            c = conn.cursor()
            c.execute("select sum(size_package),count(1) from packages")
            size, cnt = c.fetchone()
            conn.close()
        elif suffixes[-1] == ".xml":
            try:
                tree = ET.parse(tmp.name)
                root = tree.getroot()
                assert root.tag.endswith("metadata")
                cnt, size = 0, 0
                for location in root.findall(
                    "./{http://linux.duke.edu/metadata/common}package/{http://linux.duke.edu/metadata/common}size"
                ):
                    size += int(location.attrib["package"])
                    cnt += 1
            except:
                traceback.print_exc()
                return
        else:
            logger.error(f"Unknown suffix {suffixes}")
            return

        logger.info(f"Repository {path}:")
        logger.info(f"  {cnt} packages, {size} bytes in total")

        global REPO_STAT
        REPO_STAT[str(path)] = (size, cnt) if cnt > 0 else (0, 0)  # size can be None


def check_and_download(url: str, dst_file: Path) -> int:
    try:
        start = time.time()
        with requests.get(url, stream=True, timeout=(5, 10)) as r:
            r.raise_for_status()
            if "last-modified" in r.headers:
                remote_ts = parsedate_to_datetime(
                    r.headers["last-modified"]
                ).timestamp()
            else:
                remote_ts = None

            with dst_file.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1024**2):
                    if time.time() - start > DOWNLOAD_TIMEOUT:
                        raise TimeoutError("Download timeout")
                    if not chunk:
                        continue  # filter out keep-alive new chunks

                    f.write(chunk)
            if remote_ts is not None:
                os.utime(dst_file, (remote_ts, remote_ts))
        return 0
    except BaseException as e:
        logger.error(f"Error occurred: {e}")
        if dst_file.is_file():
            dst_file.unlink()
    return 1


def download_repodata(url: str, path: Path) -> int:
    path = path / "repodata"
    path.mkdir(exist_ok=True)
    oldfiles = set(path.glob("*.*"))
    newfiles = set()
    if check_and_download(url + "/repodata/repomd.xml", path / ".repomd.xml") != 0:
        logger.error(f"Failed to download the repomd.xml of {url}")
        return 1
    try:
        tree = ET.parse(path / ".repomd.xml")
        root = tree.getroot()
        assert root.tag.endswith("repomd")
        for location in root.findall(
            "./{http://linux.duke.edu/metadata/repo}data/{http://linux.duke.edu/metadata/repo}location"
        ):
            href = location.attrib["href"]
            assert len(href) > 9 and href[:9] == "repodata/"
            fn = path / href[9:]
            newfiles.add(fn)
            if check_and_download(url + "/" + href, fn) != 0:
                logger.error(f"Failed to download the {href}")
                return 1
    except BaseException as e:
        traceback.print_exc()
        return 1

    (path / ".repomd.xml").rename(path / "repomd.xml")  # update the repomd.xml
    newfiles.add(path / "repomd.xml")
    for i in oldfiles - newfiles:
        logger.info(f"Deleting old files: {i}")
        i.unlink()


def check_args(prop: str, lst: List[str]):
    for s in lst:
        if len(s) == 0 or " " in s:
            raise ValueError(f"Invalid item in {prop}: {repr(s)}")


def substitute_vars(s: str, vardict: Dict[str, str]) -> str:
    for key, val in vardict.items():
        tpl = "@{" + key + "}"
        s = s.replace(tpl, val)
    return s


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", type=str, help="base URL")
    parser.add_argument("os_version", type=str, help="e.g. 7-8,9")
    parser.add_argument(
        "component", type=str, help="e.g. mysql56-community,mysql57-community"
    )
    parser.add_argument("arch", type=str, help="e.g. x86_64,aarch64")
    parser.add_argument("repo_name", type=str, help="e.g. @{comp}-el@{os_ver}")
    parser.add_argument("working_dir", type=Path, help="working directory")
    parser.add_argument(
        "--download-repodata",
        action="store_true",
        help="download repodata files instead of generating them",
    )
    parser.add_argument(
        "--pass-arch-to-reposync",
        action="store_true",
        help="""pass --arch to reposync to further filter packages by 'arch' field in metadata (NOT recommended, prone to missing packages in some repositories, e.g. mysql)""",
    )
    args = parser.parse_args()

    raw_os_list = args.os_version.split(",")
    raw_os_list = replace_os_template(raw_os_list)
    os_list = []
    for os_version in raw_os_list:
        if "-" in os_version and "-stream" not in os_version:
            dash = os_version.index("-")
            os_list = os_list + [
                str(i)
                for i in range(int(os_version[:dash]), 1 + int(os_version[dash + 1 :]))
            ]
        else:
            os_list.append(os_version)
    check_args("os_version", os_list)
    component_list = args.component.split(",")
    check_args("component", component_list)
    arch_list = args.arch.split(",")
    check_args("arch", arch_list)

    logger.info(f"Configuration: {os_list=}, {component_list=}, {arch_list=}")

    failed = []
    args.working_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = tempfile.mkdtemp()

    def combination_os_comp(arch: str):
        for os in os_list:
            for comp in component_list:
                vardict = {
                    "arch": arch,
                    "os_ver": os,
                    "comp": comp,
                }

                name = substitute_vars(args.repo_name, vardict)
                url = substitute_vars(args.base_url, vardict)
                try:
                    probe_url = (
                        url + ("" if url.endswith("/") else "/") + "repodata/repomd.xml"
                    )
                    r = requests.head(probe_url, timeout=(7, 7))
                    if r.status_code < 400 or r.status_code == 403:
                        yield (name, url)
                    else:
                        logger.warning(f"{probe_url} -> {r.status_code}")
                except:
                    traceback.print_exc()

    for arch in arch_list:
        dest_dirs = []
        conf = tempfile.NamedTemporaryFile("w", suffix=".conf")
        conf.write(
            """
[main]
keepcache=0
"""
        )
        for name, url in combination_os_comp(arch):
            conf.write(
                f"""
[{name}]
name={name}
baseurl={url}
repo_gpgcheck=0
gpgcheck=0
enabled=1
"""
            )
            dst = (args.working_dir / name).absolute()
            dst.mkdir(parents=True, exist_ok=True)
            dest_dirs.append(dst)
        conf.flush()
        # sp.run(["cat", conf.name])
        # sp.run(["ls", "-la", cache_dir])

        if len(dest_dirs) == 0:
            logger.info("Nothing to sync")
            failed.append(("", arch))
            continue

        cmd_args = [
            "dnf",
            "reposync",
            "-c",
            conf.name,
            "--delete",
            "-p",
            str(args.working_dir.absolute()),
        ]
        if args.pass_arch_to_reposync:
            cmd_args += ["--arch", arch]
        logger.info(f"Launching dnf reposync with command: {cmd_args}")
        ret = sp.run(cmd_args)
        if ret.returncode != 0:
            failed.append((name, arch))
            continue

        for path in dest_dirs:
            path.mkdir(exist_ok=True)
            if args.download_repodata:
                download_repodata(url, path)
            else:
                shutil.rmtree(".repodata", True)
                cmd_args = [
                    "createrepo_c",
                    "--update",
                    "-v",
                    "-c",
                    cache_dir,
                    "-o",
                    str(path),
                    str(path),
                ]
                logger.info(f"Launching createrepo with command: {cmd_args}")
                ret = sp.run(cmd_args)
            calc_repo_size(path)

    if len(failed) > 0:
        logger.error(f"Failed YUM repos: {failed}")
    else:
        if len(REPO_SIZE_FILE) > 0:
            with open(REPO_SIZE_FILE, "a") as fd:
                total_size = sum([r[0] for r in REPO_STAT.values()])
                fd.write(f"+{total_size}")


if __name__ == "__main__":
    main()
