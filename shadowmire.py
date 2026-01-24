#!/usr/bin/env python

import sys
from types import FrameType
from typing import IO, Any, Callable, Generator, Literal, NoReturn, Optional
import xmlrpc.client
from dataclasses import dataclass
import re
import json
from urllib.parse import urljoin, urlparse, urlunparse, unquote
from pathlib import Path
from html.parser import HTMLParser
import logging
import html
import os
from os.path import (
    normpath,
)  # fast path computation, instead of accessing real files like pathlib
from contextlib import contextmanager
import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import signal
import tomllib
from copy import deepcopy
import functools
from http.client import HTTPConnection
import socket
from datetime import datetime, timedelta, timezone

import requests
import click
from tqdm import tqdm
from requests.adapters import HTTPAdapter, Retry

LOG_FORMAT = "%(asctime)s %(levelname)s: %(message)s (%(filename)s:%(lineno)d)"
logger = logging.getLogger("shadowmire")


USER_AGENT = "Shadowmire (https://github.com/taoky/shadowmire)"
LOCAL_DB_NAME = "local.db"
LOCAL_JSON_NAME = "local.json"
LOCAL_DB_SERIAL_NAME = "local.db.serial"

# Note that it's suggested to use only 3 workers for PyPI.
WORKERS = int(os.environ.get("SHADOWMIRE_WORKERS", "3"))
# Use threads to parallelize verification local IO
IOWORKERS = int(os.environ.get("SHADOWMIRE_IOWORKERS", "2"))
# A safety net -- to avoid upstream issues casuing too many packages removed when determinating sync plan.
MAX_DELETION = int(os.environ.get("SHADOWMIRE_MAX_DELETION", "50000"))
# Sometimes PyPI is not consistent -- new packages could not be fetched. This option tries to avoid permanently mark that kind of package as nonexist.
IGNORE_THRESHOLD = int(os.environ.get("SHADOWMIRE_IGNORE_THRESHOLD", "10000"))

# https://github.com/pypa/bandersnatch/blob/a05af547f8d1958217ef0dc0028890b1839e6116/src/bandersnatch_filter_plugins/prerelease_name.py#L18C1-L23C6
# These patterns shall work same in both re.match() and re.search(), as they begin with .+
PRERELEASE_PATTERNS = (
    re.compile(r".+rc\d+$"),
    re.compile(r".+a(lpha)?\d+$"),
    re.compile(r".+b(eta)?\d+$"),
    re.compile(r".+dev\d+$"),
)


class PackageNotFoundError(Exception):
    pass


class ExitProgramException(Exception):
    pass


def exit_handler(signum: int, frame: Optional[FrameType]) -> None:
    raise ExitProgramException


signal.signal(signal.SIGTERM, exit_handler)


def exit_with_futures(futures: dict[Future[Any], Any]) -> NoReturn:
    logger.info("Exiting...")
    for future in futures:
        future.cancel()
    sys.exit(1)


class LocalVersionKV:
    """
    A key-value database wrapper over sqlite3.

    As it would have consistency issue if it's writing while downstream is downloading the database.
    An extra "jsonpath" is used, to store kv results when necessary.
    """

    def __init__(self, dbpath: Path, jsonpath: Path) -> None:
        self.conn = sqlite3.connect(dbpath)
        self.jsonpath = jsonpath
        cur = self.conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS local(key TEXT PRIMARY KEY, value INT NOT NULL)"
        )
        self.conn.commit()

    def get(self, key: str) -> Optional[int]:
        cur = self.conn.cursor()
        res = cur.execute("SELECT value FROM local WHERE key = ?", (key,))
        row = res.fetchone()
        return row[0] if row else None

    INSERT_SQL = "INSERT INTO local (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value"

    def set(self, key: str, value: int) -> None:
        cur = self.conn.cursor()
        cur.execute(self.INSERT_SQL, (key, value))
        self.conn.commit()

    def batch_set(self, d: dict[str, int]) -> None:
        cur = self.conn.cursor()
        kvs = list(d.items())
        cur.executemany(self.INSERT_SQL, kvs)
        self.conn.commit()

    def remove(self, key: str) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM local WHERE key = ?", (key,))
        self.conn.commit()

    def remove_invalid(self) -> int:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM local WHERE value = -1")
        rowcnt = cur.rowcount
        self.conn.commit()
        return rowcnt

    def nuke(self, commit: bool = True) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM local")
        if commit:
            self.conn.commit()

    def keys(self, skip_invalid: bool = True) -> list[str]:
        cur = self.conn.cursor()
        if skip_invalid:
            res = cur.execute("SELECT key FROM local WHERE value != -1")
        else:
            res = cur.execute("SELECT key FROM local")
        rows = res.fetchall()
        return [row[0] for row in rows]

    def dump(self, skip_invalid: bool = True) -> dict[str, int]:
        cur = self.conn.cursor()
        if skip_invalid:
            res = cur.execute("SELECT key, value FROM local WHERE value != -1")
        else:
            res = cur.execute("SELECT key, value FROM local")
        rows = res.fetchall()
        return {row[0]: row[1] for row in rows}

    def dump_json(self, skip_invalid: bool = True) -> None:
        res = self.dump(skip_invalid)
        with overwrite(self.jsonpath) as f:
            json.dump(res, f, indent=2)


@contextmanager
def overwrite(
    file_path: Path, mode: str = "w", tmp_suffix: str = ".tmp"
) -> Generator[IO[Any], None, None]:
    tmp_path = file_path.parent / (file_path.name + tmp_suffix)
    try:
        with open(tmp_path, mode) as tmp_file:
            yield tmp_file
        tmp_path.rename(file_path)
    except Exception:
        # well, just keep the tmp_path in error case.
        raise


def fast_readall(file_path: Path) -> bytes:
    """
    Save some extra read(), lseek() and ioctl().
    """
    fd = os.open(file_path, os.O_RDONLY)
    if fd < 0:
        raise FileNotFoundError(file_path)
    try:
        contents = os.read(fd, file_path.stat().st_size)
        return contents
    finally:
        os.close(fd)


def normalize(name: str) -> str:
    """
    See https://peps.python.org/pep-0503/#normalized-names
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def remove_dir_with_files(directory: Path) -> None:
    """
    Remove dir in a safer (non-recursive) way, which means that the directory should have no child directories.
    """
    if not directory.exists():
        return
    assert directory.is_dir()
    for item in directory.iterdir():
        item.unlink()
    directory.rmdir()
    logger.info("Removed dir %s", directory)


def fast_iterdir(
    directory: Path | str, filter_type: Literal["dir", "file"]
) -> Generator[os.DirEntry[str], Any, None]:
    """
    iterdir() in pathlib would ignore file type information from getdents64(),
    which is not acceptable when you have millions of files in one directory,
    and you need to filter out all files/directories.
    """
    assert filter_type in ["dir", "file"]
    for item in os.scandir(directory):
        if filter_type == "dir" and item.is_dir():
            yield item
        elif filter_type == "file" and item.is_file():
            yield item


def get_package_urls_from_index_html(html_path: Path) -> list[str]:
    """
    Get all <a> href (fragments removed) from given simple/<package>/index.html contents
    """

    class ATagHTMLParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.hrefs: list[Optional[str]] = []

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            if tag == "a":
                for attr in attrs:
                    if attr[0] == "href":
                        self.hrefs.append(attr[1])

    p = ATagHTMLParser()
    contents = fast_readall(html_path).decode()
    p.feed(contents)

    ret = []
    for href in p.hrefs:
        if href:
            parsed_url = urlparse(href)
            clean_url = urlunparse(parsed_url._replace(fragment=""))
            ret.append(clean_url)
    return ret


def get_package_urls_from_index_json(json_path: Path) -> list[str]:
    """
    Get all urls from given simple/<package>/index.v1_json contents
    """
    contents = fast_readall(json_path)
    contents_dict = json.loads(contents)
    urls = [i["url"] for i in contents_dict["files"]]
    return urls


def get_package_urls_size_from_index_json(json_path: Path) -> list[tuple[str, int]]:
    """
    Get all urls and size from given simple/<package>/index.v1_json contents

    If size is not available, returns size as -1
    """
    contents = fast_readall(json_path)
    contents_dict = json.loads(contents)
    ret = [(i["url"], i.get("size", -1)) for i in contents_dict["files"]]
    return ret


def get_existing_hrefs(package_simple_path: Path) -> Optional[list[str]]:
    """
    There exists packages that have no release files, so when it encounters errors it would return None,
    otherwise empty list or list with hrefs.

    Priority: index.v1_json -> index.html
    """
    json_file = package_simple_path / "index.v1_json"
    html_file = package_simple_path / "index.html"
    try:
        return get_package_urls_from_index_json(json_file)
    except FileNotFoundError:
        try:
            return get_package_urls_from_index_html(html_file)
        except FileNotFoundError:
            return None


class CustomXMLRPCTransport(xmlrpc.client.Transport):
    """
    Set user-agent for xmlrpc.client
    """

    user_agent = USER_AGENT

    def make_connection(self, host: tuple[str, dict[str, str]] | str) -> HTTPConnection:
        conn = super().make_connection(host)
        if socket.getdefaulttimeout() is None:
            # By default conn.timeout is socket._GLOBAL_DEFAULT_TIMEOUT instead of None.
            # So here we check if default timeout is set, and if not, add a 2-min timeout
            conn.timeout = 120
        return conn


def create_requests_session() -> requests.Session:
    s = requests.Session()
    # hardcode 1min timeout for connect & read for now
    # https://requests.readthedocs.io/en/latest/user/advanced/#timeouts
    # A hack to overwrite get() method
    s.get_orig, s.get = s.get, functools.partial(s.get, timeout=(60, 60))  # type: ignore
    retries = Retry(total=3, backoff_factor=0.1)
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({"User-Agent": USER_AGENT})
    return s


class PyPI:
    """
    Upstream which implements full PyPI APIs
    """

    host = "https://pypi.org"
    # Let's assume that only sha256 exists...
    digest_name = "sha256"

    def __init__(self) -> None:
        self.xmlrpc_client = xmlrpc.client.ServerProxy(
            urljoin(self.host, "pypi"), transport=CustomXMLRPCTransport()
        )
        self.session = create_requests_session()

    def list_packages_with_serial(self, do_normalize: bool = True) -> dict[str, int]:
        logger.info(
            "Calling list_packages_with_serial() RPC, this requires some time..."
        )
        ret: dict[str, int] = self.xmlrpc_client.list_packages_with_serial()  # type: ignore
        if do_normalize:
            for key in list(ret.keys()):
                normalized_key = normalize(key)
                if normalized_key == key:
                    continue
                ret[normalized_key] = ret[key]
                del ret[key]
        return ret

    def changelog_last_serial(self) -> int:
        return self.xmlrpc_client.changelog_last_serial()  # type: ignore

    def get_package_metadata(self, package_name: str) -> dict:
        req = self.session.get(urljoin(self.host, f"pypi/{package_name}/json"))
        if req.status_code == 404:
            raise PackageNotFoundError
        return req.json()  # type: ignore

    def get_package_simple(self, package_name: str) -> dict:
        # Based on PEP 691
        headers = {"Accept": "application/vnd.pypi.simple.v1+json"}
        req = self.session.get(
            urljoin(self.host, f"simple/{package_name}/"), headers=headers
        )
        # For incorrectly configured mirrors that do not return correct content-type
        # No need for dealing with application/vnd.pypi.simple.v1+html or text/html
        # Because most of them do not support PEP 658 so we don't need this
        if req.headers.get("Content-Type", "") != "application/vnd.pypi.simple.v1+json":
            raise PackageNotFoundError
        if req.status_code == 404:
            raise PackageNotFoundError
        return req.json()  # type: ignore

    @staticmethod
    def get_release_files_from_meta(package_meta: dict) -> list[dict]:
        release_files = []
        for release in package_meta["releases"].values():
            release_files.extend(release)
        release_files.sort(key=lambda x: x["filename"])
        return release_files

    @staticmethod
    def file_url_to_local_url(url: str) -> str:
        """
        This function should NOT be used to construct a local Path!
        """
        parsed = urlparse(url)
        assert parsed.path.startswith("/packages")
        prefix = "../.."
        return prefix + parsed.path

    @staticmethod
    def file_url_to_local_path(url: str) -> Path:
        """
        Unquote() and returns a Path
        """
        path = urlparse(url).path
        path = unquote(path)
        assert path.startswith("/packages")
        path = path[1:]
        return Path("../..") / path

    # Func modified from bandersnatch
    @classmethod
    def generate_html_simple_page(cls, package_meta: dict, core_metadata_map: dict) -> str:
        package_rawname = package_meta["info"]["name"]
        simple_page_content = (
            "<!DOCTYPE html>\n"
            "<html>\n"
            "  <head>\n"
            '    <meta name="pypi:repository-version" content="{0}">\n'
            "    <title>Links for {1}</title>\n"
            "  </head>\n"
            "  <body>\n"
            "    <h1>Links for {1}</h1>\n"
        ).format("1.0", package_rawname)

        release_files = cls.get_release_files_from_meta(package_meta)

        def gen_html_file_tags(release: dict) -> str:
            file_tags = ""

            # data-requires-python: requires_python
            if "requires_python" in release and release["requires_python"] is not None:
                file_tags += (
                    f' data-requires-python="{html.escape(release["requires_python"])}"'
                )

            # data-yanked: yanked_reason
            if "yanked" in release and release["yanked"]:
                if "yanked_reason" in release and release["yanked_reason"]:
                    file_tags += (
                        f' data-yanked="{html.escape(release["yanked_reason"])}"'
                    )
                else:
                    file_tags += ' data-yanked=""'

            # data-metadata: digest_name (sha256)
            if core_metadata_map.get(release["filename"], False):
                metadata = core_metadata_map[release["filename"]]
                if cls.digest_name in metadata and metadata[cls.digest_name]:
                    file_tags += (
                        f' data-dist-info-metadata="{cls.digest_name}={html.escape(metadata[cls.digest_name])}"'
                        f' data-core-metadata="{cls.digest_name}={html.escape(metadata[cls.digest_name])}"'
                    )
                else:
                    file_tags += ' data-dist-info-metadata="true" data-core-metadata="true"'

            return file_tags

        simple_page_content += "\n".join(
            [
                '    <a href="{}#{}={}"{}>{}</a><br/>'.format(
                    cls.file_url_to_local_url(r["url"]),
                    cls.digest_name,
                    r["digests"][cls.digest_name],
                    gen_html_file_tags(r),
                    r["filename"],
                )
                for r in release_files
            ]
        )

        simple_page_content += (
            f"\n  </body>\n</html>\n<!--SERIAL {package_meta['last_serial']}-->"
        )

        return simple_page_content

    # Func modified from bandersnatch
    @classmethod
    def generate_json_simple_page(cls, package_meta: dict, core_metadata_map: dict) -> str:
        package_json: dict[str, Any] = {
            "files": [],
            "meta": {
                "api-version": "1.1",
                # not required by PEP691, but bandersnatch has it
                "_last-serial": str(package_meta["last_serial"]),
            },
            "name": package_meta["info"]["name"],
            # (bandsnatch) TODO: Just sorting by default sort - Maybe specify order in future PEP
            "versions": sorted(package_meta["releases"].keys()),
        }

        release_files = cls.get_release_files_from_meta(package_meta)

        # Add release files into the JSON dict
        for r in release_files:
            package_json["files"].append(
                {
                    "core-metadata": core_metadata_map.get(r["filename"], False),
                    "data-dist-info-metadata": core_metadata_map.get(r["filename"], False),
                    "filename": r["filename"],
                    "hashes": {
                        cls.digest_name: r["digests"][cls.digest_name],
                    },
                    "requires-python": r.get("requires_python", ""),
                    "size": r["size"],
                    "upload-time": r.get("upload_time_iso_8601", ""),
                    "url": cls.file_url_to_local_url(r["url"]),
                    "yanked": r.get("yanked", False),
                }
            )

        return json.dumps(package_json)


# (normalized_name as key, value)
ShadowmirePackageItem = tuple[str, int]


@dataclass
class Plan:
    remove: list[str]
    update: list[str]
    remote_last_serial: int


def match_patterns(
    s: str, ps: list[re.Pattern[str]] | tuple[re.Pattern[str], ...]
) -> bool:
    """
    Search if any of the patterns match the string `s`.

    Uses re.search(), matching anywhere in the string.
    """
    for p in ps:
        if p.search(s):
            return True
    return False


class PackageInclusionChecker:
    """
    A class for handling packages inclusion/exclusion based on regex patterns.
    """

    def __init__(self, exclude: tuple[str], include: tuple[str]) -> None:
        self.excludes = compile_regexes(exclude)
        self.includes = compile_regexes(include)

    def has_rules(self) -> bool:
        return bool(self.excludes or self.includes)

    def is_included(self, package_name: str) -> bool:
        if not self.has_rules():
            return True
        if self.includes:
            # Ignore excludes if includes are specified
            return match_patterns(package_name, self.includes)
        else:
            return not match_patterns(package_name, self.excludes)


class FileInclusionChecker:
    """
    A class for filtering package releases and files based on various criteria:

    - Shall this package exclude pre-releases?
    - Is this file excluded by given filename patterns?
    - Is this release yanked?
    - Is this release too old?
    """

    def __init__(
        self,
        prerelease_exclude: tuple[str],
        excluded_wheel_filename: tuple[str],
        filter_meta: bool,
        skip_yanked: bool,
        skip_old_packages_days: Optional[int],
        least_releases_to_keep: int,
    ) -> None:
        self.prerelease_excludes = compile_regexes(prerelease_exclude)
        self.excluded_wheel_filenames = compile_regexes(excluded_wheel_filename)
        self.filter_meta = filter_meta
        self.skip_yanked = skip_yanked
        self.skip_old_packages_days = skip_old_packages_days
        # Treat 0 as None...
        if self.skip_old_packages_days == 0:
            self.skip_old_packages_days = None
        self.least_releases_to_keep = least_releases_to_keep

    def has_rules(self) -> bool:
        return bool(
            self.prerelease_excludes
            or self.excluded_wheel_filenames
            or self.skip_yanked
            or self.skip_old_packages_days is not None
        )

    def get_filtered_meta(self, package_name: str, meta: dict) -> dict:
        """
        If filter_meta is True, modifies meta in place and returns it.
        Otherwise the original meta is not modified, and a filtered copy is returned.
        """
        if not self.has_rules():
            return meta
        if self.filter_meta:
            new_meta = meta
        else:
            new_meta = deepcopy(meta)

        if match_patterns(package_name, self.prerelease_excludes):
            for release in list(new_meta["releases"].keys()):
                if match_patterns(release, PRERELEASE_PATTERNS):
                    del new_meta["releases"][release]
        if self.excluded_wheel_filenames:
            for release_infos in new_meta["releases"].values():
                for release_idx in range(len(release_infos) - 1, -1, -1):
                    release_info = release_infos[release_idx]
                    filename = release_info["filename"]
                    if match_patterns(filename, self.excluded_wheel_filenames):
                        del release_infos[release_idx]
        if self.skip_yanked:
            for release_infos in new_meta["releases"].values():
                for release_idx in range(len(release_infos) - 1, -1, -1):
                    release_info = release_infos[release_idx]
                    if release_info.get("yanked", False):
                        del release_infos[release_idx]
        removed_old_release_infos: dict[str, list[tuple[datetime, dict]]] = {}
        if self.skip_old_packages_days is not None:
            threshold_date = datetime.now(timezone.utc) - timedelta(
                days=self.skip_old_packages_days
            )
            releases = new_meta["releases"]
            for release, release_infos in releases.items():
                for release_idx in range(len(release_infos) - 1, -1, -1):
                    release_info = release_infos[release_idx]
                    upload_time_str = release_info.get("upload_time_iso_8601", None)
                    if upload_time_str is None:
                        continue
                    upload_time = datetime.fromisoformat(upload_time_str)
                    if upload_time < threshold_date:
                        removed_old_release_infos.setdefault(release, []).append(
                            (upload_time, release_info)
                        )
                        del release_infos[release_idx]
            if self.least_releases_to_keep > 0:
                remaining_releases = sum(1 for infos in releases.values() if infos)
                missing = self.least_releases_to_keep - remaining_releases
                if missing > 0:
                    # Re-add the newest releases that were removed due to age.
                    candidates: list[tuple[datetime, str]] = []
                    for release, removed_infos in removed_old_release_infos.items():
                        release_infos = releases.get(release)
                        if release_infos is None or release_infos:
                            continue
                        latest_upload = max(ts for ts, _ in removed_infos)
                        candidates.append((latest_upload, release))
                    candidates.sort(reverse=True)
                    for _, release in candidates[:missing]:
                        release_infos = releases.get(release)
                        if release_infos is None:
                            continue
                        to_restore = removed_old_release_infos.get(release, [])
                        for _, info in sorted(to_restore, key=lambda x: x[0]):
                            release_infos.append(info)

        return new_meta


class SyncBase:
    def __init__(
        self, basedir: Path, local_db: LocalVersionKV, sync_packages: bool = False
    ) -> None:
        self.basedir = basedir
        self.local_db = local_db
        self.simple_dir = basedir / "simple"
        self.packages_dir = basedir / "packages"
        self.jsonmeta_dir = basedir / "json"
        # create the dirs, if not exist
        self.simple_dir.mkdir(parents=True, exist_ok=True)
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        self.jsonmeta_dir.mkdir(parents=True, exist_ok=True)
        self.sync_packages = sync_packages

    def filter_remote(
        self, remote: dict[str, int], package_inclusion_checker: PackageInclusionChecker
    ) -> dict[str, int]:
        if not package_inclusion_checker.has_rules():
            return remote
        res = {}
        for k, v in remote.items():
            if package_inclusion_checker.is_included(k):
                res[k] = v
        return res

    def determine_sync_plan(
        self, local: dict[str, int], package_inclusion_checker: PackageInclusionChecker
    ) -> Plan:
        """
        local should NOT skip invalid (-1) serials
        """
        remote_sn, remote_pkgs = self.fetch_remote_versions()
        remote_pkgs = self.filter_remote(remote_pkgs, package_inclusion_checker)
        with open(self.basedir / "remote_excluded.json", "w") as f:
            json.dump(remote_pkgs, f)

        to_remove = []
        to_update = []
        local_keys = set(local.keys())
        remote_keys = set(remote_pkgs.keys())
        for i in local_keys - remote_keys:
            to_remove.append(i)
            local_keys.remove(i)
        # There are always some packages in PyPI's list_packages_with_serial() but actually not there
        # Don't count them when comparing len(to_remove) with MAX_DELETION
        if len(to_remove) > MAX_DELETION:
            logger.error(
                "Too many packages to remove (%d > %d)", len(to_remove), MAX_DELETION
            )
            logger.info("Some packages that would be removed:")
            for p in to_remove[:100]:
                logger.info("- %s", p)
            for p in to_remove[100:]:
                logger.debug("- %s", p)
            logger.error(
                "Use SHADOWMIRE_MAX_DELETION env to adjust the threshold if you really want to proceed"
            )
            sys.exit(2)
        for i in remote_keys - local_keys:
            to_update.append(i)
        for i in local_keys:
            local_serial = local[i]
            remote_serial = remote_pkgs[i]
            if local_serial != remote_serial:
                if local_serial == -1:
                    logger.info("skip %s, as it's marked as not exist at upstream", i)
                    to_remove.append(i)
                else:
                    to_update.append(i)
        output = Plan(remove=to_remove, update=to_update, remote_last_serial=remote_sn)
        return output

    def fetch_remote_versions(self) -> tuple[int, dict[str, int]]:
        # returns (last_serial, {package_name: serial, ...})
        raise NotImplementedError

    def get_package_metadata(self, package_name: str) -> dict:
        raise NotImplementedError

    def get_package_simple(self, package_name: str) -> dict:
        raise NotImplementedError

    def get_core_metadata_map(self, simple: dict) -> dict:
        """
        get a filename to core-metadata map from simple API info for PEP 658 implementation.
        """
        files = simple.get("files", [])
        if not files:
            return {}

        file_map = {
            f["filename"]: f.get(
                "core-metadata",
                # Fallback for legacy PEP 714 attribute
                f.get("data-dist-info-metadata", False),
            )
            for f in files
        }
        return file_map

    def check_and_update(
        self,
        package_names: list[str],
        file_inclusion_checker: FileInclusionChecker,
        json_files: set[str],
        packages_pathcache: set[str],
        compare_size: bool,
    ) -> bool:
        def is_consistent(package_name: str) -> bool:
            if package_name not in json_files:
                # save a newfstatat() when name already in json_files
                logger.info("add %s as it does not have json API file", package_name)
                return False
            package_simple_path = self.simple_dir / package_name
            html_simple = package_simple_path / "index.html"
            htmlv1_simple = package_simple_path / "index.v1_html"
            json_simple = package_simple_path / "index.v1_json"
            try:
                # always create index.html symlink, if not exists or not a symlink
                if not html_simple.is_symlink():
                    html_simple.unlink(missing_ok=True)
                    html_simple.symlink_to("index.v1_html")
                hrefs_html = get_package_urls_from_index_html(htmlv1_simple)
                hrefsize_json = get_package_urls_size_from_index_json(json_simple)
            except FileNotFoundError:
                logger.info(
                    "add %s as it does not have index.v1_html or index.v1_json",
                    package_name,
                )
                return False
            if (
                hrefs_html is None
                or hrefsize_json is None
                or hrefs_html != [i[0] for i in hrefsize_json]
            ):
                # something unexpected happens...
                logger.info("add %s as its indexes are not consistent", package_name)
                return False
            # Check with JSON meta, ensuring that package file list is consistent
            json_meta_path = self.jsonmeta_dir / package_name
            try:
                with open(json_meta_path, "r") as f:
                    meta = json.load(f)
                meta = file_inclusion_checker.get_filtered_meta(package_name, meta)
                release_files = PyPI.get_release_files_from_meta(meta)
                hrefs_from_meta = {
                    PyPI.file_url_to_local_url(i["url"]) for i in release_files
                }
            except (json.JSONDecodeError, FileNotFoundError, KeyError):
                logger.info(
                    "add %s as its JSON meta is not valid",
                    package_name,
                )
                return False
            for href in hrefs_html:
                if href not in hrefs_from_meta:
                    logger.info(
                        "add %s as its HTML index has href %s not in JSON meta",
                        package_name,
                        href,
                    )
                    return False

            # OK, check if all hrefs have corresponding files
            if self.sync_packages:
                for href, size in hrefsize_json:
                    relative_path = unquote(href)
                    dest_pathstr = normpath(package_simple_path / relative_path)
                    try:
                        # Fast shortcut to avoid stat() it
                        if dest_pathstr not in packages_pathcache:
                            raise FileNotFoundError
                        if compare_size and size != -1:
                            dest = Path(dest_pathstr)
                            # So, do stat() for real only when we need to do so,
                            # have a size, and it really exists in pathcache.
                            dest_stat = dest.stat()
                            dest_size = dest_stat.st_size
                            if dest_size != size:
                                logger.info(
                                    "add %s as its local size %s != %s",
                                    package_name,
                                    dest_size,
                                    size,
                                )
                                return False
                    except FileNotFoundError:
                        logger.info("add %s as it's missing packages", package_name)
                        return False

            return True

        to_update = []
        with ThreadPoolExecutor(max_workers=IOWORKERS) as executor:
            futures = {
                executor.submit(is_consistent, package_name): package_name
                for package_name in package_names
            }
            try:
                for future in tqdm(
                    as_completed(futures),
                    total=len(package_names),
                    desc="Checking consistency",
                ):
                    package_name = futures[future]
                    try:
                        consistent = future.result()
                        if not consistent:
                            to_update.append(package_name)
                    except Exception:
                        logger.warning(
                            "%s generated an exception", package_name, exc_info=True
                        )
                        raise
            except:
                exit_with_futures(futures)

        logger.info("%s packages to update in check_and_update()", len(to_update))
        return self.parallel_update(to_update, file_inclusion_checker)

    def parallel_update(
        self,
        package_names: list[str],
        file_inclusion_checker: FileInclusionChecker,
    ) -> bool:
        success = True
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {
                executor.submit(
                    self.do_update,
                    package_name,
                    file_inclusion_checker,
                    False,
                ): (
                    idx,
                    package_name,
                )
                for idx, package_name in enumerate(package_names)
            }
            try:
                for future in tqdm(
                    as_completed(futures), total=len(package_names), desc="Updating"
                ):
                    idx, package_name = futures[future]
                    try:
                        serial = future.result()
                        if serial:
                            self.local_db.set(package_name, serial)
                    except Exception as e:
                        if isinstance(e, (KeyboardInterrupt)):
                            raise
                        logger.warning(
                            "%s generated an exception", package_name, exc_info=True
                        )
                        success = False
                    if idx % 100 == 0:
                        logger.info("dumping local db...")
                        self.local_db.dump_json()
            except (ExitProgramException, KeyboardInterrupt):
                exit_with_futures(futures)
        return success

    def do_sync_plan(
        self,
        plan: Plan,
        file_inclusion_checker: FileInclusionChecker,
    ) -> bool:
        to_remove = plan.remove
        to_update = plan.update

        for package_name in to_remove:
            self.do_remove(package_name)

        return self.parallel_update(to_update, file_inclusion_checker)

    def do_remove(
        self, package_name: str, use_db: bool = True, remove_packages: bool = True
    ) -> None:
        metajson_path = self.jsonmeta_dir / package_name
        package_simple_dir = self.simple_dir / package_name
        if metajson_path.exists() or package_simple_dir.exists():
            # To make this less noisy...
            logger.info("Removing package %s", package_name)
        packages_to_remove = get_existing_hrefs(package_simple_dir)
        if remove_packages and packages_to_remove:
            paths_to_remove = [package_simple_dir / p for p in packages_to_remove]
            for p in paths_to_remove:
                if p.exists():
                    p.unlink()
                    logger.info("Removed file %s", p)
                mp = p.with_name(p.name + ".metadata")
                if mp.exists():
                    mp.unlink()
                    logger.info("Removed metadata file %s", mp)
        remove_dir_with_files(package_simple_dir)
        metajson_path = self.jsonmeta_dir / package_name
        metajson_path.unlink(missing_ok=True)
        if use_db:
            old_serial = self.local_db.get(package_name)
            if old_serial != -1:
                self.local_db.remove(package_name)

    def do_update(
        self,
        package_name: str,
        file_inclusion_checker: FileInclusionChecker,
        use_db: bool = True,
    ) -> Optional[int]:
        raise NotImplementedError

    def write_meta_to_simple(self, package_simple_path: Path, meta: dict, core_metadata_map: dict) -> None:
        simple_html_contents = PyPI.generate_html_simple_page(meta, core_metadata_map)
        simple_json_contents = PyPI.generate_json_simple_page(meta, core_metadata_map)
        for html_filename in ("index.v1_html",):
            html_path = package_simple_path / html_filename
            with overwrite(html_path) as f:
                f.write(simple_html_contents)
        for json_filename in ("index.v1_json",):
            json_path = package_simple_path / json_filename
            with overwrite(json_path) as f:
                f.write(simple_json_contents)
        index_html_path = package_simple_path / "index.html"
        if not index_html_path.is_symlink():
            if index_html_path.exists():
                index_html_path.unlink()
            index_html_path.symlink_to("index.v1_html")

    def finalize(self, index_serial: int) -> None:
        local_names = self.local_db.keys()
        # generate v1_html index
        v1_html_index_path = self.basedir / "simple" / "index.v1_html"
        # modified from bandersnatch
        with overwrite(v1_html_index_path) as f:
            f.write("<!DOCTYPE html>\n")
            f.write("<html>\n")
            f.write("  <head>\n")
            f.write('    <meta name="pypi:repository-version" content="1.0">\n')
            f.write("    <title>Simple Index</title>\n")
            f.write("  </head>\n")
            f.write("  <body>\n")
            # This will either be the simple dir, or if we are using index
            # directory hashing, a list of subdirs to process.
            for pkg in local_names:
                # We're really trusty that this is all encoded in UTF-8. :/
                f.write(f'    <a href="{pkg}/">{pkg}</a><br/>\n')
            f.write("  </body>\n</html>")
        # always link index.html to index.v1_html
        html_simple_path = self.basedir / "simple" / "index.html"
        if not html_simple_path.is_symlink():
            html_simple_path.unlink(missing_ok=True)
            html_simple_path.symlink_to("index.v1_html")

        # generate v1_json index and local.db{,.serial} for downstream use
        v1_json_index_path = self.basedir / "simple" / "index.v1_json"
        with overwrite(v1_json_index_path) as f:
            index_json: dict[str, Any] = {
                "meta": {
                    "api-version": "1.1",
                    "_last-serial": index_serial,
                },
                "projects": [{"name": n} for n in sorted(local_names)],
            }
            json.dump(index_json, f)
        with overwrite(self.basedir / LOCAL_DB_SERIAL_NAME) as f:
            f.write(str(index_serial))
        self.local_db.dump_json()

    def skip_this_package(self, i: dict, dest: Path) -> bool:
        """
        A helper function for subclasses implementing do_update().
        As existence check is also done with stat(), this would not bring extra I/O overhead.
        Returns if skip this package or not.
        """
        try:
            dest_size = dest.stat().st_size
            i_size = i.get("size", -1)
            if i_size == -1:
                return True
            if dest_size == i_size:
                return True
            logger.warning(
                "file %s exists locally, but size does not match with upstream, so it would still be downloaded.",
                dest,
            )
            return False
        except FileNotFoundError:
            return False


def download(
    session: requests.Session, url: str, dest: Path
) -> tuple[bool, Optional[requests.Response]]:
    try:
        resp = session.get(url, allow_redirects=True)
    except requests.RequestException:
        logger.warning("download %s failed with exception", exc_info=True)
        return False, None
    if resp.status_code >= 400:
        logger.warning(
            "download %s failed with status %s, skipping this package",
            url,
            resp.status_code,
        )
        return False, resp
    with overwrite(dest, "wb") as f:
        f.write(resp.content)
    return True, resp


class SyncPyPI(SyncBase):
    def __init__(
        self, basedir: Path, local_db: LocalVersionKV, sync_packages: bool = False
    ) -> None:
        self.pypi = PyPI()
        self.session = create_requests_session()
        self.last_serial: Optional[int] = None
        self.remote_packages: Optional[dict[str, int]] = None
        super().__init__(basedir, local_db, sync_packages)

    def fetch_remote_versions(self) -> tuple[int, dict[str, int]]:
        self.last_serial = self.pypi.changelog_last_serial()
        self.remote_packages = self.pypi.list_packages_with_serial()
        logger.info("Remote has %s packages", len(self.remote_packages))
        with overwrite(self.basedir / "remote.json") as f:
            json.dump(self.remote_packages, f)
            logger.info("File saved to remote.json.")
        return self.last_serial, self.remote_packages

    def get_package_metadata(self, package_name: str) -> dict:
        return self.pypi.get_package_metadata(package_name)

    def get_package_simple(self, package_name: str) -> dict:
        return self.pypi.get_package_simple(package_name)

    def do_update(
        self,
        package_name: str,
        file_inclusion_checker: FileInclusionChecker,
        use_db: bool = True,
    ) -> Optional[int]:
        logger.info("updating %s", package_name)
        package_simple_path = self.simple_dir / package_name
        package_simple_path.mkdir(exist_ok=True)
        try:
            meta_original = self.get_package_metadata(package_name)
            logger.debug("%s meta: %s", package_name, meta_original)
        except PackageNotFoundError:
            if (
                self.remote_packages is not None
                and package_name in self.remote_packages
            ):
                recorded_serial = self.remote_packages[package_name]
            else:
                recorded_serial = None
            if (
                recorded_serial is not None
                and self.last_serial is not None
                and abs(recorded_serial - self.last_serial) < IGNORE_THRESHOLD
            ):
                logger.warning(
                    "%s missing from upstream (its serial %s, remote last serial %s), try next time...",
                    package_name,
                    recorded_serial,
                    self.last_serial,
                )
                return None

            logger.warning(
                "%s missing from upstream (its serial %s, remote last serial %s), remove and ignore in the future.",
                package_name,
                recorded_serial,
                self.last_serial,
            )
            # try remove it locally, if it does not exist upstream
            self.do_remove(package_name, use_db=False)
            if not use_db:
                return -1
            self.local_db.set(package_name, -1)
            return None

        core_metadata_map = {}
        try:
            simple = self.get_package_simple(package_name)
            core_metadata_map = self.get_core_metadata_map(simple)
        except PackageNotFoundError:
            # Some mirrors may not implement PEP 691 simple API, just go ahead
            pass
        # filter prerelease and wheel files, if necessary
        meta = file_inclusion_checker.get_filtered_meta(package_name, meta_original)

        if self.sync_packages:
            # sync packages first, then sync index
            existing_hrefs = get_existing_hrefs(package_simple_path)
            existing_hrefs = [] if existing_hrefs is None else existing_hrefs
            release_files = PyPI.get_release_files_from_meta(meta)
            # remove packages that no longer exist remotely
            remote_hrefs = [PyPI.file_url_to_local_url(i["url"]) for i in release_files]
            should_remove = list(set(existing_hrefs) - set(remote_hrefs))
            for href in should_remove:
                p = unquote(href)
                logger.info("removing file %s (if exists)", p)
                package_path = Path(normpath(package_simple_path / p))
                package_path.unlink(missing_ok=True)
                # Also remove associated metadata file
                metadata_path = package_path.with_name(package_path.name + ".metadata")
                metadata_path.unlink(missing_ok=True)
            for i in release_files:
                url = i["url"]
                dest = Path(
                    normpath(
                        package_simple_path / self.pypi.file_url_to_local_path(i["url"])
                    )
                )
                logger.info("downloading file %s -> %s", url, dest)
                if self.skip_this_package(i, dest):
                    continue

                dest.parent.mkdir(parents=True, exist_ok=True)
                success, _resp = download(self.session, url, dest)
                if not success:
                    logger.warning("skipping %s as it fails downloading", package_name)
                    return None

                # PEP 658: Download metadata file if available
                if core_metadata_map.get(i["filename"], False):
                    m_url = url + ".metadata"
                    m_dest = dest.with_name(dest.name + ".metadata")
                    logger.info("downloading metadata %s -> %s", m_url, m_dest)
                    m_success, m_resp = download(
                        self.session, m_url, m_dest
                    )
                    if not m_success:
                        logger.warning("ignoring %s metadata as it fails downloading", package_name)

        last_serial: int = meta["last_serial"]

        self.write_meta_to_simple(package_simple_path, meta, core_metadata_map)
        json_meta_path = self.jsonmeta_dir / package_name
        with overwrite(json_meta_path) as f:
            json.dump(meta_original, f)

        if use_db:
            self.local_db.set(package_name, last_serial)

        return last_serial


class SyncPlainHTTP(SyncBase):
    def __init__(
        self,
        upstream: str,
        basedir: Path,
        local_db: LocalVersionKV,
        sync_packages: bool = False,
        use_pypi_index: bool = False,
    ) -> None:
        self.upstream = upstream
        self.session = create_requests_session()
        self.pypi: Optional[PyPI]
        if use_pypi_index:
            self.pypi = PyPI()
        else:
            self.pypi = None
        super().__init__(basedir, local_db, sync_packages)

    def fetch_remote_versions(self) -> tuple[int, dict[str, int]]:
        remote_pkgs: dict[str, int]
        if not self.pypi:
            remote_pkg_db_url = urljoin(self.upstream, LOCAL_JSON_NAME)
            resp = self.session.get(remote_pkg_db_url)
            resp.raise_for_status()
            remote_pkgs = resp.json()
            # first fallback to max serial in remote_pkgs
            serial = max(remote_pkgs.values()) if remote_pkgs else -1
            # then try to get last serial from remote
            remote_last_serial_url = urljoin(self.upstream, LOCAL_DB_SERIAL_NAME)
            try:
                resp = self.session.get(remote_last_serial_url)
                resp.raise_for_status()
                serial = int(resp.text.strip())
            except (requests.RequestException, ValueError):
                logger.warning(
                    f"cannot get last_serial from upstream, fallback to max package serial in {LOCAL_JSON_NAME}",
                    exc_info=True,
                )
        else:
            serial = self.pypi.changelog_last_serial()
            remote_pkgs = self.pypi.list_packages_with_serial()
        logger.info("Remote has %s packages", len(remote_pkgs))
        with overwrite(self.basedir / "remote.json") as f:
            json.dump(remote_pkgs, f)
            logger.info("File saved to remote.json.")
        return serial, remote_pkgs

    def get_package_metadata(self, package_name: str) -> dict:
        file_url = urljoin(self.upstream, f"json/{package_name}")
        success, resp = download(
            self.session, file_url, self.jsonmeta_dir / (package_name + ".new")
        )
        if not success:
            logger.error(
                "download %s JSON meta fails with code %s",
                package_name,
                resp.status_code if resp else None,
            )
            raise PackageNotFoundError
        assert resp
        return resp.json()

    def get_package_simple(self, package_name: str) -> dict:
        if not self.pypi:
            # Use shadowmire static file first for less consumption
            req = self.session.get(
                urljoin(self.upstream, f"simple/{package_name}/index.v1_json")
            )
            if req.status_code == 404:
                raise PackageNotFoundError
            return req.json()  # type: ignore
        else:
            return self.pypi.get_package_simple(package_name)

    def do_update(
        self,
        package_name: str,
        file_inclusion_checker: FileInclusionChecker,
        use_db: bool = True,
    ) -> Optional[int]:
        logger.info("updating %s", package_name)
        package_simple_path = self.simple_dir / package_name
        package_simple_path.mkdir(exist_ok=True)
        if self.sync_packages:
            hrefs = get_existing_hrefs(package_simple_path)
            existing_hrefs = [] if hrefs is None else hrefs
        # Download JSON meta
        try:
            meta_original = self.get_package_metadata(package_name)
        except PackageNotFoundError:
            return None
        core_metadata_map = {}
        try:
            simple = self.get_package_simple(package_name)
            core_metadata_map = self.get_core_metadata_map(simple)
        except PackageNotFoundError:
            # Some mirrors may not implement PEP 691 simple API, just go ahead
            pass
        # filter prerelease and wheel files, if necessary
        meta = file_inclusion_checker.get_filtered_meta(package_name, meta_original)

        if self.sync_packages:
            release_files = PyPI.get_release_files_from_meta(meta)
            remote_hrefs = [PyPI.file_url_to_local_url(i["url"]) for i in release_files]
            should_remove = list(set(existing_hrefs) - set(remote_hrefs))
            for href in should_remove:
                p = unquote(href)
                logger.info("removing file %s (if exists)", p)
                package_path = Path(normpath(package_simple_path / p))
                package_path.unlink(missing_ok=True)
                # Also remove associated metadata file
                metadata_path = package_path.with_name(package_path.name + ".metadata")
                metadata_path.unlink(missing_ok=True)
            package_simple_url = urljoin(self.upstream, f"simple/{package_name}/")
            for i in release_files:
                href = PyPI.file_url_to_local_url(i["url"])
                path = PyPI.file_url_to_local_path(i["url"])
                url = urljoin(package_simple_url, href)
                dest = Path(normpath(package_simple_path / path))
                logger.info("downloading file %s -> %s", url, dest)
                if self.skip_this_package(i, dest):
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                success, resp = download(self.session, url, dest)
                if not success:
                    if resp and resp.status_code == 404:
                        # handle special case: upstream filters out some files
                        logger.warning(
                            "cannot find %s at upstream, fallback to pypi", url
                        )
                        url = i["url"]  # original pypi URL
                        success, resp = download(self.session, url, dest)
                        if not success:
                            logger.warning(
                                "skipping %s as it fails downloading (from pypi)",
                                package_name,
                            )
                            return None
                    else:
                        logger.warning(
                            "skipping %s as it fails downloading", package_name
                        )
                        return None

                # PEP 658: Download metadata file if available
                if core_metadata_map.get(i["filename"], False):
                    # Try from upstream first, then fallback to PyPI if needed
                    m_url = url + ".metadata"
                    m_dest = dest.with_name(dest.name + ".metadata")
                    logger.info("downloading metadata %s -> %s", m_url, m_dest)
                    m_success, m_resp = download(self.session, m_url, m_dest)
                    if not m_success:
                        if m_resp and m_resp.status_code == 404:
                            pypi_m_url = i["url"] + ".metadata"
                            logger.warning(
                                "cannot find metadata %s at upstream, fallback to pypi",
                                m_url,
                            )
                            m_success, m_resp = download(
                                self.session, pypi_m_url, m_dest
                            )
                            if not m_success:
                                logger.warning(
                                    "ignoring %s metadata as it fails downloading (from pypi)",
                                    package_name,
                                )
                        else:
                            logger.warning(
                                "ignoring %s metadata as it fails downloading", package_name
                            )

        # OK, now it's safe to rename
        (self.jsonmeta_dir / (package_name + ".new")).rename(
            self.jsonmeta_dir / package_name
        )
        # generate indexes
        self.write_meta_to_simple(package_simple_path, meta_original, core_metadata_map)

        last_serial: int = meta["last_serial"]
        if use_db:
            self.local_db.set(package_name, last_serial)

        return last_serial


def get_local_serial(package_meta_direntry: os.DirEntry[str]) -> Optional[int]:
    """
    Accepts /json/<package_name> as package_meta_path
    """
    package_name = package_meta_direntry.name
    try:
        contents = fast_readall(Path(package_meta_direntry.path))
    except FileNotFoundError:
        logger.warning("%s does not have JSON metadata, skipping", package_name)
        return None
    try:
        meta = json.loads(contents)
        return meta["last_serial"]  # type: ignore
    except Exception:
        logger.warning("cannot parse %s's JSON metadata", package_name, exc_info=True)
        return None


def sync_shared_args(func: Callable[..., Any]) -> Callable[..., Any]:
    shared_options = [
        click.option(
            "--sync-packages/--no-sync-packages",
            default=False,
            help="Sync packages instead of just indexes, by default it's --no-sync-packages",
        ),
        click.option(
            "--shadowmire-upstream",
            required=False,
            type=str,
            help="Use another upstream using shadowmire instead of PyPI",
        ),
        click.option(
            "--use-pypi-index/--no-use-pypi-index",
            default=False,
            help="Always use PyPI index metadata (via XMLRPC). It's a no-op without --shadowmire-upstream. Some packages might not be downloaded successfully. Defaults to false.",
        ),
        click.option(
            "--exclude",
            multiple=True,
            help="Remote package names to exclude (regex patterns).",
        ),
        click.option(
            "--include",
            multiple=True,
            help="Only include these remote package names (regex patterns). If set, --exclude is ignored.",
        ),
        click.option(
            "--prerelease-exclude",
            multiple=True,
            help="Package names of which prereleases will be excluded (regex patterns).",
        ),
        click.option(
            "--excluded-wheel-filename",
            multiple=True,
            help="Specify patterns to exclude wheel files (applies to all packages, regex patterns).",
        ),
        click.option(
            "--filter-metadata/--no-filter-metadata",
            default=True,
            help="Whether to modify each package's metadata according to release and file filtering rules. Defaults to true.",
        ),
        click.option(
            "--skip-yanked/--no-skip-yanked",
            default=False,
            help="Whether to skip yanked release files when syncing packages. Defaults to false.",
        ),
        click.option(
            "--skip-old-packages-days",
            default=None,
            type=int,
            help="Skip files whose upload time is earlier than the specified number of days. Defaults to None (do not skip any).",
        ),
        click.option(
            "--least-releases-to-keep",
            default=0,
            type=int,
            help="If --skip-old-packages-days ignores too many releases, at least keep this many latest releases while respecting other rules. Defaults to 0 (do not enforce).",
        ),
    ]

    @functools.wraps(func)
    @click.pass_context
    def wrapper(ctx: click.Context, *args, **kwargs):
        package_inclusion_checker = PackageInclusionChecker(
            exclude=kwargs.pop("exclude"),
            include=kwargs.pop("include"),
        )
        file_inclusion_checker = FileInclusionChecker(
            prerelease_exclude=kwargs.pop("prerelease_exclude"),
            excluded_wheel_filename=kwargs.pop("excluded_wheel_filename"),
            filter_meta=kwargs.pop("filter_metadata"),
            skip_yanked=kwargs.pop("skip_yanked"),
            skip_old_packages_days=kwargs.pop("skip_old_packages_days"),
            least_releases_to_keep=kwargs.pop("least_releases_to_keep"),
        )
        kwargs["package_inclusion_checker"] = package_inclusion_checker
        kwargs["file_inclusion_checker"] = file_inclusion_checker
        return ctx.invoke(func, *args, **kwargs)

    decorated = wrapper
    for opt in reversed(shared_options):
        decorated = opt(decorated)
    return decorated


def read_config(
    ctx: click.Context, param: click.Option, filename: Optional[str]
) -> None:
    # Set default repo as cwd
    ctx.default_map = {}
    ctx.default_map["repo"] = "."

    if filename is None:
        return
    with open(filename, "rb") as f:
        data = tomllib.load(f)
    try:
        options = dict(data["options"])
    except KeyError:
        options = {}
    if options.get("repo"):
        ctx.default_map["repo"] = options["repo"]
        del options["repo"]

    logger.info("Read options from %s: %s", filename, options)

    ctx.default_map["sync"] = options
    ctx.default_map["verify"] = options
    ctx.default_map["do-update"] = options
    ctx.default_map["do-remove"] = options


@click.group()
@click.option(
    "--config",
    type=click.Path(dir_okay=False),
    help="Read option defaults from specified TOML file",
    callback=read_config,
    expose_value=False,
)
@click.option("--repo", type=click.Path(file_okay=False), help="Repo (basedir) path")
@click.pass_context
def cli(ctx: click.Context, repo: str) -> None:
    log_level = logging.DEBUG if os.environ.get("DEBUG") else logging.INFO
    logging.basicConfig(level=log_level, format=LOG_FORMAT)
    ctx.ensure_object(dict)

    if WORKERS > 10:
        logger.warning(
            "You have set a worker value larger than 10, which is forbidden by PyPI maintainers."
        )
        logger.warning("Don't blame me if you were banned!")

    # Make sure basedir is absolute
    basedir = Path(repo).resolve()
    local_db = LocalVersionKV(basedir / LOCAL_DB_NAME, basedir / LOCAL_JSON_NAME)
    ctx.obj["basedir"] = basedir
    ctx.obj["local_db"] = local_db


def compile_regexes(exclude: tuple[str]) -> list[re.Pattern[str]]:
    return [re.compile(i) for i in exclude]


def get_syncer(
    basedir: Path,
    local_db: LocalVersionKV,
    sync_packages: bool,
    shadowmire_upstream: Optional[str],
    use_pypi_index: bool,
) -> SyncBase:
    syncer: SyncBase
    if shadowmire_upstream:
        syncer = SyncPlainHTTP(
            upstream=shadowmire_upstream,
            basedir=basedir,
            local_db=local_db,
            sync_packages=sync_packages,
            use_pypi_index=use_pypi_index,
        )
    else:
        syncer = SyncPyPI(
            basedir=basedir, local_db=local_db, sync_packages=sync_packages
        )
    return syncer


@cli.command(help="Sync from upstream")
@click.pass_context
@sync_shared_args
def sync(
    ctx: click.Context,
    sync_packages: bool,
    shadowmire_upstream: Optional[str],
    package_inclusion_checker: PackageInclusionChecker,
    file_inclusion_checker: FileInclusionChecker,
    use_pypi_index: bool,
) -> None:
    basedir: Path = ctx.obj["basedir"]
    local_db: LocalVersionKV = ctx.obj["local_db"]
    syncer = get_syncer(
        basedir, local_db, sync_packages, shadowmire_upstream, use_pypi_index
    )
    local = local_db.dump(skip_invalid=False)
    plan = syncer.determine_sync_plan(local, package_inclusion_checker)
    # save plan for debugging
    with overwrite(basedir / "plan.json") as f:
        json.dump(plan, f, default=vars, indent=2)
    success = syncer.do_sync_plan(plan, file_inclusion_checker)
    syncer.finalize(plan.remote_last_serial)

    logger.info("Synchronization finished. Success: %s", success)

    if not success:
        sys.exit(1)


@cli.command(help="(Re)generate local db and json from json/")
@click.pass_context
def genlocal(ctx: click.Context) -> None:
    basedir: Path = ctx.obj["basedir"]
    local_db: LocalVersionKV = ctx.obj["local_db"]
    local = {}
    json_dir = basedir / "json"
    logger.info("Iterating all items under %s", json_dir)
    dir_items = [d for d in fast_iterdir(json_dir, "file")]
    logger.info("Detected %s packages in %s in total", len(dir_items), json_dir)
    with ThreadPoolExecutor(max_workers=IOWORKERS) as executor:
        futures = {
            executor.submit(get_local_serial, package_metapath): package_metapath
            for package_metapath in dir_items
        }
        try:
            for future in tqdm(
                as_completed(futures),
                total=len(dir_items),
                desc="Reading packages from json/",
            ):
                package_name = futures[future].name
                try:
                    serial = future.result()
                    if serial:
                        local[package_name] = serial
                except Exception as e:
                    if isinstance(e, (KeyboardInterrupt)):
                        raise
                    logger.warning(
                        "%s generated an exception", package_name, exc_info=True
                    )
        except (ExitProgramException, KeyboardInterrupt):
            exit_with_futures(futures)
    logger.info(
        "%d out of %d packages have valid serial number", len(local), len(dir_items)
    )
    local_db.nuke(commit=False)
    local_db.batch_set(local)
    local_db.dump_json()


@cli.command(
    help="Verify existing sync from local db, download missing things, remove unreferenced packages"
)
@click.pass_context
@sync_shared_args
@click.option(
    "--remove-not-in-local", is_flag=True, help="Do step 1 instead of skipping"
)
@click.option(
    "--compare-size",
    is_flag=True,
    help="Instead of just check if it exists, also compare local package size when possible, to decide if local package file is valid",
)
def verify(
    ctx: click.Context,
    sync_packages: bool,
    shadowmire_upstream: Optional[str],
    package_inclusion_checker: PackageInclusionChecker,
    file_inclusion_checker: FileInclusionChecker,
    remove_not_in_local: bool,
    compare_size: bool,
    use_pypi_index: bool,
) -> None:
    basedir: Path = ctx.obj["basedir"]
    local_db: LocalVersionKV = ctx.obj["local_db"]
    syncer = get_syncer(
        basedir, local_db, sync_packages, shadowmire_upstream, use_pypi_index
    )

    logger.info("====== Step 1. Remove packages NOT in local db ======")
    local_names = set(local_db.keys())
    simple_dirs = {i.name for i in fast_iterdir((basedir / "simple"), "dir")}
    json_files = {i.name for i in fast_iterdir((basedir / "json"), "file")}
    not_in_local = (simple_dirs | json_files) - local_names
    logger.info(
        "%d out of %d local packages NOT in local db",
        len(not_in_local),
        len(local_names),
    )
    for package_name in not_in_local:
        logger.info("package %s not in local db", package_name)
        if remove_not_in_local:
            # Old bandersnatch would download packages without normalization,
            # in which case one package file could have multiple "packages"
            # with different names, but normalized to the same one.
            # So, when in verify, we always set remove_packages=False
            # In step 4 unreferenced files would be removed, anyway.
            syncer.do_remove(package_name, remove_packages=False)

    logger.info("====== Step 2. Remove packages NOT in remote index ======")
    local = local_db.dump(skip_invalid=False)
    plan = syncer.determine_sync_plan(local, package_inclusion_checker)
    logger.info(
        "%s packages NOT in remote index -- this might contain packages that also do not exist locally",
        len(plan.remove),
    )
    for package_name in plan.remove:
        # We only take the plan.remove part here
        logger.info("package %s not in remote index", package_name)
        syncer.do_remove(package_name, remove_packages=False)

    # After some removal, local_names is changed.
    local_names = set(local_db.keys())

    logger.info("====== Step 3. Caching packages/ dirtree in memory for Step 4 & 5.")
    packages_pathcache: set[str] = set()
    with ThreadPoolExecutor(max_workers=IOWORKERS) as executor:

        def packages_iterate(first_dirname: str, position: int) -> list[str]:
            with tqdm(
                desc=f"Iterating packages/{first_dirname}/*/*/*", position=position
            ) as pb:
                res = []
                for d1 in fast_iterdir(basedir / "packages" / first_dirname, "dir"):
                    for d2 in fast_iterdir(d1.path, "dir"):
                        for file in fast_iterdir(d2.path, "file"):
                            pb.update(1)
                            res.append(file.path)
                return res

        futures = {
            executor.submit(
                packages_iterate, first_dir.name, idx % IOWORKERS
            ): first_dir.name  # type: ignore
            for idx, first_dir in enumerate(fast_iterdir((basedir / "packages"), "dir"))
        }
        try:
            for future in as_completed(futures):
                sname = futures[future]
                try:
                    for p in future.result():
                        packages_pathcache.add(p)
                except Exception as e:
                    if isinstance(e, (KeyboardInterrupt)):
                        raise
                    logger.warning("%s generated an exception", sname, exc_info=True)
                    success = False
        except (ExitProgramException, KeyboardInterrupt):
            exit_with_futures(futures)

    logger.info(
        "====== Step 4. Make sure all local indexes are valid, and (if --sync-packages) have valid local package files ======"
    )
    success = syncer.check_and_update(
        list(local_names),
        file_inclusion_checker,
        json_files,
        packages_pathcache,
        compare_size,
    )
    syncer.finalize(plan.remote_last_serial)

    logger.info(
        "====== Step 5. Remove any unreferenced files in `packages` folder ======"
    )
    ref_set: set[str] = set()
    with ThreadPoolExecutor(max_workers=IOWORKERS) as executor:
        # Part 1: iterate simple/
        def iterate_simple(sname: str) -> list[str]:
            sd = basedir / "simple" / sname
            hrefs = get_existing_hrefs(sd)
            hrefs = [] if hrefs is None else hrefs
            nps = []
            for href in hrefs:
                i = unquote(href)
                # use normpath, which is much faster than pathlib resolve(), as it does not need to access fs
                # we could make sure no symlinks could affect this here
                np = normpath(sd / i)
                logger.debug("add to ref_set: %s", np)
                nps.append(np)
                # also add metadata file to reference set if it exists
                metadata_path = Path(np + ".metadata")
                if metadata_path.exists():
                    metadata_np = str(metadata_path)
                    logger.debug("add to ref_set: %s", metadata_np)
                    nps.append(metadata_np)
            return nps

        # MyPy does not enjoy same variable name with different types, even when --allow-redefinition
        # Ignore here to make mypy happy
        futures = {
            executor.submit(iterate_simple, sname): sname
            for sname in simple_dirs  # type: ignore
        }
        try:
            for future in tqdm(
                as_completed(futures),
                total=len(simple_dirs),
                desc="Iterating simple/ directory",
            ):
                sname = futures[future]
                try:
                    nps = future.result()
                    for np in nps:
                        ref_set.add(np)
                except Exception as e:
                    if isinstance(e, (KeyboardInterrupt)):
                        raise
                    logger.warning("%s generated an exception", sname, exc_info=True)
                    success = False
        except (ExitProgramException, KeyboardInterrupt):
            exit_with_futures(futures)

        # Part 2: handling packages
        for path in tqdm(packages_pathcache, desc="Iterating path cache"):
            if path not in ref_set:
                logger.info("removing unreferenced file %s", path)
                Path(path).unlink(missing_ok=True)

    logger.info("Verification finished. Success: %s", success)

    if not success:
        sys.exit(1)


@cli.command(help="Manual update given package for debugging purpose")
@click.pass_context
@sync_shared_args
@click.argument("package_name")
def do_update(
    ctx: click.Context,
    sync_packages: bool,
    shadowmire_upstream: Optional[str],
    package_inclusion_checker: PackageInclusionChecker,
    file_inclusion_checker: FileInclusionChecker,
    use_pypi_index: bool,
    package_name: str,
) -> None:
    basedir: Path = ctx.obj["basedir"]
    local_db: LocalVersionKV = ctx.obj["local_db"]
    if package_inclusion_checker.has_rules():
        logger.warning("package filter rules are ignored in do_update()")
    syncer = get_syncer(
        basedir, local_db, sync_packages, shadowmire_upstream, use_pypi_index
    )
    syncer.do_update(package_name, file_inclusion_checker)


@cli.command(help="Manual remove given package for debugging purpose")
@click.pass_context
@sync_shared_args
@click.argument("package_name")
def do_remove(
    ctx: click.Context,
    sync_packages: bool,
    shadowmire_upstream: Optional[str],
    package_inclusion_checker: PackageInclusionChecker,
    file_inclusion_checker: FileInclusionChecker,
    use_pypi_index: bool,
    package_name: str,
) -> None:
    basedir = ctx.obj["basedir"]
    local_db = ctx.obj["local_db"]
    if package_inclusion_checker.has_rules() or file_inclusion_checker.has_rules():
        logger.warning("package or file filter rules are ignored in do_remove()")
    syncer = get_syncer(
        basedir, local_db, sync_packages, shadowmire_upstream, use_pypi_index
    )
    syncer.do_remove(package_name)


@cli.command(help="Call pypi list_packages_with_serial() for debugging")
@click.pass_context
def list_packages_with_serial(ctx: click.Context) -> None:
    basedir = ctx.obj["basedir"]
    local_db = ctx.obj["local_db"]
    syncer = SyncPyPI(basedir, local_db)
    syncer.fetch_remote_versions()


@cli.command(help="Clear invalid package status in local database")
@click.pass_context
def clear_invalid_packages(ctx: click.Context) -> None:
    local_db: LocalVersionKV = ctx.obj["local_db"]
    total = local_db.remove_invalid()
    logger.info("Removed %s invalid status in local database", total)


if __name__ == "__main__":
    cli(obj={})
