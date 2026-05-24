#!/usr/bin/env python3
"""
pip-index.py - Mirror script for pip-style HTTP package indexes.

Adapted from ustclug/ustcmirror-images pytorch/sync.py (originally
pytorch.py). Crawls PEP 503 / PEP 691 simple HTML indexes recursively
and rewrites href attributes so saved index pages point back to this
mirror. Used by the pytorch and jetson-pypi tunasync jobs; the same
script is mounted into tunathu/tunasync-scripts:latest via docker_volumes.

Additions on top of the upstream script:
  - Multi-host href rewrite (download.pytorch.org + download-r2.pytorch.org).
  - EXTRA_REWRITES so hrefs to other hosts (e.g. files.pythonhosted.org)
    can be redirected to a sibling local mirror prefix (e.g. /pypi/web).
  - DEVPI_MODE: query devpi channel JSON API to crawl only that channel's
    own projects via .../<channel>/+simple/<project>/ instead of walking
    the full inherited PyPI namespace.
  - Switched httpx -> aiohttp so it runs inside the shared
    tunathu/tunasync-scripts:latest image with no extra dependencies.

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
  REWRITE_HOSTS              Comma-separated upstream hosts whose absolute
                             hrefs should be rewritten to URLBASE. Hrefs
                             starting with "/" are always rewritten too.
                             Defaults to the host of TUNASYNC_UPSTREAM_URL.
  EXTRA_REWRITES             Comma-separated "host=prefix" rules for hrefs
                             of OTHER hosts, e.g.
                             "files.pythonhosted.org=/pypi/web".
                             Default empty.
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
  TIMEOUT                    Per-request total timeout (seconds).
                             Default "120".
  DRY_RUN                    "1" -> log only, do not write anything.
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
HREF_RE = re.compile(r'href="([^"]+)"')


base = Path(os.environ.get("TO", os.environ.get("TUNASYNC_WORKING_DIR", ".")))
dry_run = os.environ.get("DRY_RUN", "0") == "1"
jobs = int(os.environ.get("JOBS", "1"))
timeout_sec = int(os.environ.get("TIMEOUT", "120"))

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

# REWRITE_HOSTS defaults to the host of TUNASYNC_UPSTREAM_URL when unset.
upstream_url = os.environ.get("TUNASYNC_UPSTREAM_URL", "")
if upstream_url:
    default_hosts = urlparse(upstream_url).netloc
else:
    default_hosts = "download.pytorch.org,download-r2.pytorch.org"
rewrite_hosts = [
    h.strip()
    for h in os.environ.get("REWRITE_HOSTS", default_hosts).split(",")
    if h.strip()
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
    extra_rewrites.append((host, prefix))
# exclude nightly builds, by default
no_nightly = os.environ.get("NO_NIGHTLY", "1") == "1"

sem = asyncio.Semaphore(jobs)
# Track URLs we have already started processing so links from cross-referenced
# index pages do not cause duplicate work or infinite recursion.
visited: set[str] = set()


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
        except Exception:
            if attempt == 2:
                raise
            logging.warning(f"Failed to download {url}, retrying ({attempt + 1})...")
            await asyncio.sleep(5)
    assert False, "impossible"


async def stream_to_file(
    client: aiohttp.ClientSession, url: str, dest: Path
) -> None:
    """Stream `url` to `dest` via a sibling .tmp file. Memory-bounded."""
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
                            await asyncio.to_thread(fh.write, chunk)
                finally:
                    progress_task.cancel()
                    try:
                        await progress_task
                    except asyncio.CancelledError:
                        pass
            os.replace(tmp, dest)
            return
        except Exception:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            if attempt == 2:
                raise
            logging.warning(f"Failed to download {url}, retrying ({attempt + 1})...")
            await asyncio.sleep(5)


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


def rewrite_index(index_resp: str) -> str:
    """Rewrite href attributes so the saved index page points at this mirror."""
    # Relative-from-root form: href="/whl/..." -> href="<URLBASE>whl/..."
    index_resp = index_resp.replace('href="/', f'href="{urlbase}')
    # Absolute upstream URLs from any rewrite host.
    for host in rewrite_hosts:
        index_resp = index_resp.replace(
            f'href="https://{host}/', f'href="{urlbase}'
        )
        index_resp = index_resp.replace(
            f'href="http://{host}/', f'href="{urlbase}'
        )
    # Absolute URLs from OTHER hosts that have an explicit local prefix
    # (e.g. files.pythonhosted.org -> /pypi/web/). See Issue #86.
    for host, prefix in extra_rewrites:
        index_resp = index_resp.replace(
            f'href="https://{host}/', f'href="{prefix}'
        )
        index_resp = index_resp.replace(
            f'href="http://{host}/', f'href="{prefix}'
        )
    return index_resp


async def recursive_download(client: aiohttp.ClientSession, url: str):
    # Skip URLs we already started processing. Index pages frequently link
    # back into themselves and cross-link wheel artifacts; without this the
    # crawl could grow exponentially or even loop.
    if url in visited:
        return
    visited.add(url)

    raw_path = unquote(urlparse(url).path)
    if url.endswith("/") or url.endswith(".html"):
        # index.html (current) or torch_stable.html (old)
        async with sem:
            logging.info(f"Getting {url}")
            contents = await get_with_progress(client, url)
            index_resp = contents.decode("utf-8")
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

        # Derive the upstream base (scheme://netloc) from the current url so
        # absolute-from-root hrefs ("/whl/foo") can be resolved without
        # hardcoding download.pytorch.org.
        parsed = urlparse(url)
        upstream_base = f"{parsed.scheme}://{parsed.netloc}"

        tasks = []
        for m in A_RE.finditer(index_resp):
            attr = m.group(1)
            href = HREF_RE.search(attr)
            assert href is not None, f"Invalid href in {attr}"
            suburl = href.group(1).split("#")[0]
            if suburl.startswith("/"):
                suburl = urljoin(upstream_base, suburl)
            else:
                suburl = urljoin(url, suburl)
            if suburl in visited:
                continue
            tasks.append(asyncio.create_task(recursive_download(client, suburl)))
            if suburl.endswith(".whl") and "data-core-metadata" in attr:
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
            index_resp = rewrite_index(index_resp)
            index_dir.mkdir(parents=True, exist_ok=True)
            with overwrite(index_dir / filename, "w") as f:
                f.write(index_resp)
    else:
        dest = safe_local_path(base, raw_path)
        if dest.exists():
            return
        if not dry_run:
            async with sem:
                logging.info(f"Downloading {url} to {dest}")
                try:
                    await stream_to_file(client, url, dest)
                except aiohttp.ClientResponseError as e:
                    # Some urls are blocked by upstream, e.g.,
                    # https://download.pytorch.org/whl/cu128/
                    # nvidia_cudnn_cu12-9.8.0.87-py3-none-manylinux_2_27_aarch64.whl
                    # This is a workaround to skip those files.
                    if e.status == 403:
                        logging.warning(f"Forbidden: {url}, skipping.")
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


async def main():
    timeout_obj = aiohttp.ClientTimeout(total=timeout_sec)
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

        await asyncio.gather(*(recursive_download(client, url) for url in urls))


if __name__ == "__main__":
    asyncio.run(main())
