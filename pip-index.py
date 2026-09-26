#!/usr/bin/env python3
"""
pip-index.py - Mirror script for pip-style HTTP package indexes.

Adapted from ustclug/ustcmirror-images pytorch/sync.py (originally
pytorch.py). Crawls PEP 503 simple HTML indexes recursively and rewrites
href attributes so saved index pages point back to this mirror. Used by
the pytorch, rocm-pypi and jetson-pypi tunasync jobs; the same script is
mounted into tunathu/tunasync-scripts:latest via docker_volumes.

Additions on top of the upstream script:
  - Rewrite-all href policy: every absolute href is rewritten to URLBASE
    regardless of host (multi-host upstreams like download-r2.pytorch.org,
    pypi.nvidia.com, repo.amd.com need no configuration).
  - EXTRA_REWRITES so hrefs to other hosts (e.g. files.pythonhosted.org)
    can be redirected to a sibling local mirror prefix (e.g. /pypi/web).
  - DEVPI_MODE: query devpi channel JSON API to crawl only that channel's
    own projects via .../<channel>/+simple/<project>/ instead of walking
    the full inherited PyPI namespace.
  - CLEANUP: optionally delete stale local files no crawled URL maps to
    (safety-capped by CLEANUP_MAX_DELETE); files that returned 404 are
    treated as yanked and removed too (capped by CLEANUP_MAX_404_DELETE).
  - Cross-host collision guard: artifacts and index pages are keyed by
    URL path only (preserving the existing data layout); when the same
    path is linked from two different hosts, the later URL is logged as
    an error and skipped instead of silently overwriting the earlier one.
  - REVALIDATE: HEAD-check files that already exist locally so yanked
    (404) or republished same-name artifacts do not stay stale forever
    (default on when CLEANUP=1).
  - Switched httpx -> aiohttp (python3-aiohttp, provided by the repo
    Dockerfile / tunathu/tunasync-scripts image).

Compatible with: PyTorch download server, NVIDIA Jetson AI Lab pypi
(devpi-backed), and other PEP 503 simple HTML indexes that emit
<a href="..."> per file.

Not for: pypi.org full mirroring (use shadowmire.py), Conda channels,
apt / yum repositories, git or docker registries.

Environment variables:
  TO / TUNASYNC_WORKING_DIR  Mirror data directory (tunasync injects).
  TUNASYNC_MIRROR_NAME       Mirror name (tunasync injects). Used as the
                             default URLBASE when URLBASE is unset.
  URLBASE                    Local URL prefix used when rewriting hrefs.
                             Defaults to "/<TUNASYNC_MIRROR_NAME>/".
                             Always normalised to leading + trailing "/".
                             Every absolute http(s) href is rewritten to
                             this prefix by default (the crawler downloads
                             every linked file regardless of host, so the
                             rewrite covers every host too).
  EXTRA_REWRITES             Comma-separated "host=prefix" rules for hrefs
                             of OTHER hosts, e.g.
                             "files.pythonhosted.org=/pypi/web".
                             Files on these hosts are NOT downloaded; they are
                             expected to be served by the sibling local mirror
                             at <prefix> (equivalent to ustclug PR #174's
                             PYPI_URLBASE). Default empty.
  USE_PYTORCH_RELEASES       PyTorch-only. "1" -> additionally consume
                             pytorch.github.io releases.json (or
                             published_versions.json with GET_ALL=1) to
                             discover extra index pages. Default "0".
  GET_ALL                    PyTorch-only, with USE_PYTORCH_RELEASES=1.
                             "1" -> use published_versions.json (full).
                             "0" -> use releases.json (recommended).
  DEVPI_MODE                 "1" -> treat each ".../<channel>/+simple/"
                             entry in CUSTOM_ENDPOINTS as a devpi channel
                             and crawl only its own projects via JSON.
                             Falls back to PEP 503 if the JSON call fails.
                             Default "0".
  CUSTOM_ENDPOINTS           Comma-separated list of additional index URLs
                             to crawl. Required for non-PyTorch upstreams.
  NO_NIGHTLY                 "1" -> skip URLs containing "/nightly/".
                             Default "1".
  JOBS                       Concurrent download semaphore. Default "1".
  TIMEOUT                    Socket read (idle) timeout per request, in
                             seconds. There is no total cap, so multi-GB
                             wheels finish at any speed; connect timeout is
                             fixed at 30s. Default "120".
  DRY_RUN                    "1" -> log only, do not write anything.
  CLEANUP                    "1" -> after crawling, delete local files that
                             no crawled URL maps to (stale/yanked content,
                             leftover .tmp). Index subtrees skipped due to
                             403/404 and (with NO_NIGHTLY=1) nightly paths
                             are never deleted. Files that returned 404 are
                             deleted as yanked upstream; 403 stays protected
                             (blocks may be transient). Default "0".
  CLEANUP_MAX_DELETE         Safety cap: CLEANUP refuses to delete anything
                             when stale candidates exceed this count.
                             Default "1000".
  CLEANUP_MAX_404_DELETE     Safety cap for 404 deletions: when more files
                             return 404 than this count, they are kept
                             (a mass-404 event looks like upstream breakage,
                             not yanking). Default "100".
  REVALIDATE                 "1" -> HEAD-check files that already exist
                             locally: 404 -> treat as yanked (fed to
                             CLEANUP's gone_files), changed Content-Length
                             -> redownload. Roughly doubles request volume
                             with cheap HEADs, still bounded by JOBS.
                             Default "1" when CLEANUP=1, else "0".
  https_proxy / HTTPS_PROXY  Honoured automatically (aiohttp trust_env).
"""

from contextlib import contextmanager
from typing import IO, Any, Generator
import aiohttp
from pathlib import Path
import os
import re
from urllib.parse import urlparse, urljoin, unquote
import asyncio
import time
import logging

LOG_FORMAT = "%(asctime)s %(levelname)s: %(message)s (%(filename)s:%(lineno)d)"
log_level = logging.DEBUG if os.environ.get("DEBUG") else logging.INFO
logging.basicConfig(level=log_level, format=LOG_FORMAT)

# PyTorch-specific GitHub raw URLs, only used when USE_PYTORCH_RELEASES=1.
RELEASES_URL = "https://raw.githubusercontent.com/pytorch/pytorch.github.io/refs/heads/site/releases.json"
PUBLISHED_VERSION_URL = "https://raw.githubusercontent.com/pytorch/pytorch.github.io/refs/heads/site/published_versions.json"
A_RE = re.compile(r"<a ([^>]*)>")
HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']")
HREF_FULL_RE = re.compile(r"href=([\"'])([^\"']+)\1")


base = Path(os.environ.get("TO", os.environ.get("TUNASYNC_WORKING_DIR", ".")))
dry_run = os.environ.get("DRY_RUN", "0") == "1"
jobs = int(os.environ.get("JOBS", "1"))
timeout_sec = int(os.environ.get("TIMEOUT", "120"))
cleanup = os.environ.get("CLEANUP", "0") == "1"
cleanup_max_delete = int(os.environ.get("CLEANUP_MAX_DELETE", "1000"))
cleanup_max_404_delete = int(os.environ.get("CLEANUP_MAX_404_DELETE", "100"))
# HEAD-check existing files: catches yanked (404) and republished (size
# changed) same-name artifacts. Default on for CLEANUP runs so yanks are
# actually detected; off for plain incremental runs to halve requests.
revalidate = os.environ.get("REVALIDATE", "1" if cleanup else "0") == "1"

# URLBASE defaults to /<TUNASYNC_MIRROR_NAME>/ when unset.
mirror_name = os.environ.get("TUNASYNC_MIRROR_NAME", "")
default_urlbase = f"/{mirror_name}/" if mirror_name else "/pytorch/"
urlbase = os.environ.get("URLBASE", default_urlbase)
if not urlbase.endswith("/"):
    urlbase += "/"
if not urlbase.startswith("/"):
    urlbase = "/" + urlbase

# if true, additionally read PyTorch releases.json / published_versions.json
use_pytorch_releases = os.environ.get("USE_PYTORCH_RELEASES", "0") == "1"
# if true, use PUBLISHED_VERSION_URL to get the list of URLs (only with USE_PYTORCH_RELEASES=1)
get_all = os.environ.get("GET_ALL", "0") == "1"
# if true, expand devpi channel endpoints via JSON API
devpi_mode = os.environ.get("DEVPI_MODE", "0") == "1"
# allow custom endpoints, e.g., https://download.pytorch.org/whl/xpu (Intel GPU builds)
custom_endpoints = [
    e.strip() for e in os.environ.get("CUSTOM_ENDPOINTS", "").split(",") if e.strip()
]

# EXTRA_REWRITES: host=prefix rules to rewrite hrefs of OTHER hosts to
# different mirror prefixes. See docstring for usage and Issue #86 context.
extra_rewrites: list[tuple[str, str]] = []
for rule in os.environ.get("EXTRA_REWRITES", "").split(","):
    rule = rule.strip()
    if not rule:
        continue
    if "=" not in rule:
        logging.warning(f"Ignoring invalid EXTRA_REWRITES rule: {rule!r}")
        continue
    host, prefix = rule.split("=", 1)
    host = host.strip()
    prefix = prefix.strip()
    if not host or not prefix:
        logging.warning(f"Ignoring invalid EXTRA_REWRITES rule: {rule!r}")
        continue
    if not prefix.endswith("/"):
        prefix += "/"
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    extra_rewrites.append((host.lower(), prefix))
# exclude nightly builds, by default
no_nightly = os.environ.get("NO_NIGHTLY", "1") == "1"

sem = asyncio.Semaphore(jobs)
# Track URLs we have already started processing so links from cross-referenced
# index pages do not cause duplicate work or infinite recursion.
visited: set[str] = set()
# Local directories whose index pages were skipped due to upstream 403/404.
# Their contents are unreachable this run but still exist upstream, so
# CLEANUP must not treat them as stale.
forbidden_dirs: set[Path] = set()
# First-seen origin (scheme, host, path) of each local destination (index
# pages and artifacts alike). Local files are keyed by URL path only (the
# existing data layout), so the same path served by two different hosts
# would collide at one dest, sharing one .tmp file. The later URL is skipped
# with an error instead of silently overwriting or corrupting the earlier
# download.
dest_origins: dict[Path, tuple[str, str, str]] = {}
# Local files whose download returned 404 (gone/yanked upstream). CLEANUP
# drops them from the allowlist so their stale local copies can be removed.
# 403 stays protected: a block may be transient, a 404 is definitive.
gone_files: set[Path] = set()
# Bytes downloaded this run, summed for the closing "Total size is ..."
# log line that tunasync's size_pattern parses (same as github-release.py).
total_bytes = 0


def sizeof_fmt(num: float, suffix: str = "iB") -> str:
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < 1024.0:
            return "%3.2f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.2f%s%s" % (num, "Y", suffix)


def safe_local_path(base_dir: Path, raw_path: str) -> Path:
    """Resolve `raw_path` against `base_dir` and reject path traversal.

    URL path components are unquoted and joined to `base_dir`. The resolved
    path is then required to live below `base_dir` so a hostile upstream
    cannot escape the mirror via '..' or absolute components.
    """
    while raw_path.startswith("/"):
        raw_path = raw_path[1:]
    candidate = (base_dir / raw_path).resolve()
    base_resolved = base_dir.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError(f"refusing path outside base: {candidate}") from exc
    return candidate


def claim_dest(dest: Path, url: str) -> bool:
    """Register `url` as the origin of local `dest`; False on conflict.

    Local destinations are keyed by the (unquoted) URL path only, so two
    different URLs — from different hosts, or with same-host paths that
    normalize alike ("/foo%2Fbar" vs "/foo/bar", dot-segment variants) —
    can collide at one dest and share one .tmp file, letting concurrent
    writers overwrite/corrupt each other. Only an exact re-claim of the
    same origin (scheme, host, path) is accepted; anything else is logged
    and rejected. Applies to artifacts and index pages alike.
    """
    parsed = urlparse(url)
    origin = (parsed.scheme, parsed.netloc.lower(), parsed.path)
    existing = dest_origins.get(dest)
    if existing is None:
        dest_origins[dest] = origin
        return True
    if existing == origin:
        return True
    logging.error(
        f"Skipping {url}: destination {dest} is already mirrored from "
        f"{existing[0]}://{existing[1]}{existing[2]}"
    )
    return False


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


async def show_progress(url, start_time, get_downloaded, total):
    try:
        while True:
            await asyncio.sleep(5)
            downloaded = get_downloaded()
            elapsed = time.monotonic() - start_time
            if total > 0:
                logging.info(
                    f"Progress of {url}: {downloaded}/{total} "
                    f"({downloaded / total:.2%}), elapsed: {elapsed:.0f}s"
                )
            else:
                logging.info(
                    f"Progress of {url}: {downloaded} bytes, elapsed: {elapsed:.0f}s"
                )
    except asyncio.CancelledError:
        pass


async def get_with_progress(client: aiohttp.ClientSession, url: str) -> bytes:
    """Fetch `url` fully into memory. Use only for index pages."""
    for attempt in range(3):
        try:
            async with client.get(url, allow_redirects=True) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0

                progress_task = asyncio.create_task(
                    show_progress(url, time.monotonic(), lambda: downloaded, total)
                )
                chunks = []
                try:
                    async for chunk in resp.content.iter_chunked(65536):
                        downloaded += len(chunk)
                        chunks.append(chunk)
                finally:
                    progress_task.cancel()
                    try:
                        await progress_task
                    except asyncio.CancelledError:
                        pass
                return b"".join(chunks)
        except Exception as e:
            # Blocked (403) or yanked (404) upstream: retrying cannot help
            # and would just stall the crawl while holding the semaphore.
            if attempt == 2 or (
                isinstance(e, aiohttp.ClientResponseError) and e.status in (403, 404)
            ):
                raise
            logging.warning(f"Failed to download {url}, retrying ({attempt + 1})...")
            await asyncio.sleep(5)
    assert False, "impossible"


async def stream_to_file(
    client: aiohttp.ClientSession, url: str, dest: Path
) -> int:
    """Stream `url` to `dest` via a sibling .tmp file. Memory-bounded.

    Returns the number of bytes written.
    """
    for attempt in range(3):
        tmp = dest.parent / (dest.name + ".tmp")
        try:
            async with client.get(url, allow_redirects=True) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                progress_task = asyncio.create_task(
                    show_progress(url, time.monotonic(), lambda: downloaded, total)
                )
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with open(tmp, "wb") as fh:
                        async for chunk in resp.content.iter_chunked(65536):
                            downloaded += len(chunk)
                            fh.write(chunk)
                finally:
                    progress_task.cancel()
                    try:
                        await progress_task
                    except asyncio.CancelledError:
                        pass
            os.replace(tmp, dest)
            return downloaded
        except Exception as e:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            # Blocked (403) or yanked (404) upstream: retrying cannot help
            # and would just stall the crawl while holding the semaphore.
            if attempt == 2 or (
                isinstance(e, aiohttp.ClientResponseError) and e.status in (403, 404)
            ):
                raise
            logging.warning(f"Failed to download {url}, retrying ({attempt + 1})...")
            await asyncio.sleep(5)
    assert False, "impossible"


async def get_devpi_projects(
    client: aiohttp.ClientSession, channel_url: str
) -> list[str] | None:
    """Query a devpi channel via JSON API for its own projects.

    Returns a list of project names owned by the channel, or None if the
    upstream does not look like devpi or the request fails.
    """
    try:
        async with client.get(
            channel_url,
            headers={"Accept": "application/json"},
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        return None
    projects = result.get("projects")
    if not isinstance(projects, list):
        return None
    return [p for p in projects if isinstance(p, str) and p]


def rewrite_index(index_resp: str, page_url: str) -> str:
    """Rewrite href attributes so the saved index page points at this mirror.

    EVERY absolute http(s) href is rewritten to URLBASE by default: the
    crawler downloads every linked file regardless of host, so the rewrite
    must cover every host too — otherwise pip silently bypasses the mirror
    whenever the upstream starts linking from a new host (seen with
    files.pythonhosted.org in Issue #86, pypi.nvidia.com, repo.amd.com).
    Hosts listed in EXTRA_REWRITES are the exception: their hrefs map to
    their own local prefix and the files are served by that sibling mirror.

    Exception: an href whose URL lost a destination collision this run
    (another URL claimed the same local path first) is kept as-is, so
    clients fetch it from the upstream host directly instead of receiving
    the other URL's file under a mismatched #sha256 fragment.
    """
    page = urlparse(page_url)

    def replace(m: "re.Match[str]") -> str:
        quote, value = m.group(1), m.group(2)
        if value.startswith(("http://", "https://")):
            abs_url = value
        elif value.startswith("//"):
            abs_url = f"{page.scheme}:{value}"
        elif value.startswith("/"):
            abs_url = f"{page.scheme}://{page.netloc}{value}"
        else:
            # Relative and fragment-only hrefs stay untouched.
            return m.group(0)
        parsed = urlparse(abs_url)
        host = parsed.netloc.lower()
        # Same local-path mapping recursive_download uses, so collision
        # losers (a different URL claimed this dest first) can be spotted.
        try:
            dest = safe_local_path(base, unquote(parsed.path))
            if parsed.path.endswith("/"):
                dest = dest / "index.html"
        except ValueError:
            return m.group(0)
        winner = dest_origins.get(dest)
        if winner is not None and winner != (parsed.scheme, host, parsed.path):
            return m.group(0)
        prefix = urlbase
        for h, p in extra_rewrites:
            if host == h:
                prefix = p
                break
        # Rebuild the URL on the local prefix, keeping query and fragment
        # (pip relies on the "#sha256=..." fragment for hash checking).
        local = f"{prefix}{parsed.path.lstrip('/')}"
        if parsed.query:
            local += f"?{parsed.query}"
        if parsed.fragment:
            local += f"#{parsed.fragment}"
        return f"href={quote}{local}{quote}"

    return HREF_FULL_RE.sub(replace, index_resp)


async def recursive_download(client: aiohttp.ClientSession, url: str):
    global total_bytes
    # Skip URLs we already started processing. Index pages frequently link
    # back into themselves and cross-link wheel artifacts; without this the
    # crawl could grow exponentially or even loop.
    if url in visited:
        return
    visited.add(url)

    raw_path = unquote(urlparse(url).path)
    if url.endswith("/") or url.endswith(".html"):
        # index.html (current) or torch_stable.html (old)
        if url.endswith("/"):
            filename = "index.html"
            # Treat the directory portion as the local path so we do not
            # turn the .html filename into a directory.
            index_dir = safe_local_path(base, raw_path)
        else:
            filename = url.split("/")[-1]
            assert filename.endswith(".html"), f"Unexpected HTML file: {filename}"
            # `raw_path` already includes the .html filename. Strip it so
            # `index_dir` is the parent directory.
            parent = raw_path.rsplit("/", 1)[0] if "/" in raw_path else ""
            index_dir = safe_local_path(base, parent)
        # Index pages share the collision guard with artifacts: two hosts
        # exposing the same path (e.g. both "/simple/") must not overwrite
        # the same index.html through a shared .tmp concurrently.
        if not claim_dest(index_dir / filename, url):
            return
        async with sem:
            logging.info(f"Getting {url}")
            try:
                contents = await get_with_progress(client, url)
            except aiohttp.ClientResponseError as e:
                # Some index pages are blocked by upstream too, e.g.
                # https://download.pytorch.org/whl/rocm7.14/cuda-bindings/
                # A 404 means the project/index vanished upstream.
                # Skip the whole subtree, same as blocked files below.
                if e.status in (403, 404):
                    logging.warning(f"HTTP {e.status}: {url}, skipping.")
                    if url.endswith("/"):
                        forbidden_dirs.add(safe_local_path(base, raw_path))
                    else:
                        parent = raw_path.rsplit("/", 1)[0] if "/" in raw_path else ""
                        forbidden_dirs.add(safe_local_path(base, parent))
                    return
                raise
            index_resp = contents.decode("utf-8")

        tasks = []
        for m in A_RE.finditer(index_resp):
            attr = m.group(1)
            href = HREF_RE.search(attr)
            if href is None:
                # Anchors like <a name=...> carry no href; skip them.
                continue
            suburl = href.group(1).split("#")[0]
            # urljoin resolves relative, root-relative and protocol-relative
            # hrefs against the page URL all by itself.
            suburl = urljoin(url, suburl)
            if suburl in visited:
                continue
            if no_nightly and "/nightly/" in suburl:
                continue
            tasks.append(asyncio.create_task(recursive_download(client, suburl)))
            if suburl.endswith(".whl") and (
                "data-dist-info-metadata" in attr or "data-core-metadata" in attr
            ):
                meta_url = suburl + ".metadata"
                if meta_url not in visited:
                    tasks.append(
                        asyncio.create_task(
                            recursive_download(client, meta_url)
                        )
                    )
        if tasks:
            await asyncio.gather(*tasks)
        if not dry_run:
            index_resp = rewrite_index(index_resp, url)
            index_dir.mkdir(parents=True, exist_ok=True)
            with overwrite(index_dir / filename, "w") as f:
                f.write(index_resp)
    else:
        # Files on EXTRA_REWRITES hosts are served by a sibling local mirror
        # (e.g. files.pythonhosted.org -> /pypi/web), so only rewrite hrefs
        # and never download them here. Equivalent to ustclug PR #174's
        # PYPI_URLBASE behaviour.
        url_host = urlparse(url).netloc.lower()
        if any(url_host == host for host, _ in extra_rewrites):
            logging.info(f"Skipping download of {url} (EXTRA_REWRITES host)")
            return
        dest = safe_local_path(base, raw_path)
        if not claim_dest(dest, url):
            return
        if dest.exists():
            if dry_run or not revalidate:
                return
            # An existing file is not necessarily up to date: upstream may
            # have yanked it (404) or republished it under the same name,
            # and pip would fail the #sha256 check on a stale copy. HEAD is
            # cheap; requests stay bounded by sem/JOBS. Best-effort: any
            # transient error keeps the local copy instead of aborting.
            async with sem:
                try:
                    async with client.head(url, allow_redirects=True) as resp:
                        status = resp.status
                        remote_len = resp.headers.get("Content-Length")
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logging.warning(
                        f"Revalidation failed for {url} ({e}), keeping existing file."
                    )
                    return
            if status == 404:
                logging.warning(f"HTTP 404 on revalidation: {url}, treating as yanked.")
                gone_files.add(dest)
                return
            if status == 403:
                # Blocked, maybe transient: keep the local copy, and keep it
                # protected from CLEANUP (not added to gone_files).
                logging.warning(f"HTTP 403 on revalidation: {url}, keeping existing file.")
                return
            if status != 200:
                logging.warning(f"HTTP {status} on revalidation: {url}, keeping existing file.")
                return
            if remote_len is None:
                logging.warning(f"No Content-Length for {url}, keeping existing file.")
                return
            if int(remote_len) == dest.stat().st_size:
                return
            logging.info(
                f"Size changed for {url} "
                f"({dest.stat().st_size} -> {remote_len} bytes), redownloading."
            )
        if not dry_run:
            async with sem:
                logging.info(f"Downloading {url} to {dest}")
                try:
                    total_bytes += await stream_to_file(client, url, dest)
                except aiohttp.ClientResponseError as e:
                    # Some urls are blocked by upstream, e.g.,
                    # https://download.pytorch.org/whl/cu128/
                    # nvidia_cudnn_cu12-9.8.0.87-py3-none-manylinux_2_27_aarch64.whl
                    # A 403 may be transient (referer/ACL blocks), so the
                    # local copy stays protected from CLEANUP. A 404 means
                    # the file vanished upstream (yanked): record it so
                    # CLEANUP can remove the stale local copy.
                    if e.status == 404:
                        logging.warning(f"HTTP 404: {url}, skipping.")
                        gone_files.add(dest)
                    elif e.status == 403:
                        logging.warning(f"HTTP 403: {url}, skipping.")
                    else:
                        raise


async def expand_devpi_endpoint(
    client: aiohttp.ClientSession, endpoint: str
) -> list[str]:
    """Expand a devpi-style "<channel>/+simple/" endpoint into per-project
    "<channel>/+simple/<project>/" URLs.

    Returns the expanded URL list. If the endpoint does not look like a
    devpi channel or the JSON API is unavailable, returns [endpoint] so
    the caller falls back to PEP 503 crawling.
    """
    if "/+simple/" not in endpoint:
        return [endpoint]
    channel_url = endpoint.split("/+simple/", 1)[0]
    projects = await get_devpi_projects(client, channel_url)
    if projects is None:
        logging.warning(
            f"DEVPI_MODE: cannot get projects for {channel_url}, "
            "falling back to PEP 503 crawl"
        )
        return [endpoint]
    base_simple = endpoint
    if not base_simple.endswith("/"):
        base_simple += "/"
    expanded = [f"{base_simple}{p}/" for p in projects]
    logging.info(
        f"DEVPI_MODE: expanded {channel_url} to {len(expanded)} project endpoints"
    )
    return expanded


def cleanup_stale_files() -> None:
    """Delete local files that no crawled URL maps to (CLEANUP=1).

    `visited` holds every URL this run started processing; each maps to a
    local file by the same rules recursive_download uses. Anything else
    under `base` is stale (removed/yanked upstream, leftover .tmp, ...).
    Refuses to delete more than CLEANUP_MAX_DELETE files in one run so a
    partial crawl cannot wipe the tree. Subtrees whose index page was
    skipped due to 403/404, and (with NO_NIGHTLY=1) nightly paths, are never
    candidates: unreachable this run does not mean gone upstream.

    Files whose download returned 404 ARE gone upstream (yanked), so they
    are removed from the allowlist and their stale local copies become
    candidates — unless their count exceeds CLEANUP_MAX_404_DELETE, which
    looks like an upstream mass-404 event rather than ordinary yanking and
    keeps them protected. 403 stays protected: blocks may be transient.
    """
    expected: set[Path] = set()
    for url in visited:
        raw_path = unquote(urlparse(url).path)
        try:
            if url.endswith("/"):
                expected.add(safe_local_path(base, raw_path) / "index.html")
            else:
                expected.add(safe_local_path(base, raw_path))
        except ValueError:
            continue

    if gone_files:
        if len(gone_files) > cleanup_max_404_delete:
            logging.error(
                f"CLEANUP: {len(gone_files)} files returned 404, exceeding "
                f"CLEANUP_MAX_404_DELETE={cleanup_max_404_delete}; keeping "
                "them (possible upstream mass-404 event)"
            )
        else:
            logging.info(
                f"CLEANUP: {len(gone_files)} files gone upstream (404), "
                "eligible for deletion"
            )
            expected -= gone_files

    root = base.resolve()
    candidates: list[Path] = []
    excluded_forbidden = 0
    excluded_nightly = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            p = Path(dirpath) / name
            if p in expected:
                continue
            if no_nightly and "/nightly/" in str(p):
                excluded_nightly += 1
                continue
            if any(p.is_relative_to(d) for d in forbidden_dirs):
                excluded_forbidden += 1
                continue
            candidates.append(p)
    logging.info(
        f"CLEANUP: {len(candidates)} stale candidates "
        f"(excluded {excluded_forbidden} under 403/404 subtrees, "
        f"{excluded_nightly} nightly)"
    )
    if len(candidates) > cleanup_max_delete:
        logging.error(
            f"CLEANUP: {len(candidates)} candidates exceed "
            f"CLEANUP_MAX_DELETE={cleanup_max_delete}, refusing to delete"
        )
        return
    for p in candidates[:20]:
        logging.info(f"CLEANUP: stale file {p}")
    if len(candidates) > 20:
        logging.info(f"CLEANUP: ... and {len(candidates) - 20} more")
    if dry_run:
        return
    for p in candidates:
        p.unlink()
    # Prune directories left empty, bottom-up.
    for dirpath, _dirnames, _filenames in os.walk(root, topdown=False):
        d = Path(dirpath)
        if d == root:
            continue
        try:
            d.rmdir()
        except OSError:
            pass
    logging.info(f"CLEANUP: deleted {len(candidates)} stale files")


async def main():
    # No total cap: a multi-GB wheel cannot fit a fixed total timeout (and
    # a timeout would retry from zero, then abort the whole run). Bound
    # connect/read idle time instead, like apt-sync.py's (30, 60) timeouts.
    timeout_obj = aiohttp.ClientTimeout(
        total=None, sock_connect=30, sock_read=timeout_sec
    )
    connector = aiohttp.TCPConnector(limit=jobs)
    async with aiohttp.ClientSession(
        headers={
            "User-Agent": "pip-index-sync"
        },
        timeout=timeout_obj,
        connector=connector,
        trust_env=True,
    ) as client:
        urls = set()

        def add_endpoint(url: str):
            if no_nightly and "/nightly/" in url:
                logging.info(f"Skipping nightly build: {url}")
                return
            if url.endswith(".html"):
                urls.add(url)
            else:
                if not url.endswith("/"):
                    url += "/"
                urls.add(url)

        if devpi_mode:
            for endpoint in custom_endpoints:
                expanded = await expand_devpi_endpoint(client, endpoint)
                for u in expanded:
                    add_endpoint(u)
        else:
            for endpoint in custom_endpoints:
                add_endpoint(endpoint)

        if use_pytorch_releases:
            if not get_all:
                logging.info("Getting releases info from GitHub...")
                async with client.get(RELEASES_URL) as resp:
                    resp.raise_for_status()
                    releases = await resp.json(content_type=None)
                releases = releases["release"]

                for os_ in releases:
                    for version in releases[os_]:
                        url = version["installation"].split(" ")[-1]
                        if not url.startswith("https://download.pytorch.org"):
                            continue
                        if url.startswith("https://download.pytorch.org/whl/"):
                            add_endpoint(url)
            else:
                logging.info("Getting published versions from GitHub...")
                async with client.get(PUBLISHED_VERSION_URL) as resp:
                    resp.raise_for_status()
                    published_versions = await resp.json(content_type=None)
                published_versions = published_versions["versions"]

                def find_commands(obj: dict) -> list[str]:
                    commands = []
                    assert isinstance(obj, dict), f"unexpected JSON schema {obj}"
                    for key, value in obj.items():
                        if key == "command" and value is not None:
                            assert isinstance(value, str), f"unexpected command {value}"
                            commands.append(value)
                        elif isinstance(value, dict):
                            commands.extend(find_commands(value))
                    return commands

                for command in find_commands(published_versions):
                    command = command.split(" ")[-1]
                    if command.startswith("https://download.pytorch.org/whl/"):
                        add_endpoint(command)

        if not urls:
            logging.warning(
                "No URLs to crawl. Set CUSTOM_ENDPOINTS or USE_PYTORCH_RELEASES=1."
            )
            return

        # Sorted for determinism: when two URLs collide at one local
        # destination the first claim wins, so seed order must not depend
        # on set iteration.
        await asyncio.gather(*(recursive_download(client, url) for url in sorted(urls)))

    if cleanup:
        cleanup_stale_files()
    # tunasync's size_pattern parses this line (same as github-release.py).
    logging.info(f"Total size is {sizeof_fmt(total_bytes, suffix='')}")


if __name__ == "__main__":
    asyncio.run(main())
