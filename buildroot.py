#!/usr/bin/env python3
"""Buildroot sources.buildroot.net mirror -- self-contained incremental sync.

Why this exists:
  sources.buildroot.net (the official backup site) has permanently disabled
  directory listing (Cloudflare 403).  Neither rsync, tsumugu, nor wget -m
  can discover what files exist on the server.

  This script clones the buildroot git tree, extracts the download URL for
  every package directly from the .mk files, and downloads only new or
  changed files.  Existing local data (478G as of 2025-02) is preserved.

How it works:
  1. Shallow-clone buildroot master
  2. Parse boot/*.mk, linux/*.mk, package/*/*.mk for VERSION, SITE, SOURCE
  3. Expand version variables, Kconfig mirror defaults, and macro calls
     (github, gitlab, sourceforge; git/svn/cargo/go filename suffixes)
  4. Compare each candidate URL against the local mirror
  5. Download new/changed files atomically (.tmp -> rename), trying the
     backup site (TUNASYNC_UPSTREAM_URL) first and the package's own site
     second -- the backup copy is canonical for this mirror
  6. Optional cleanup of stale files up to TUNASYNC_BUILDROOT_MAXDELETE

Design constraints:
  - Only adds files; cleanup is opt-in via TUNASYNC_BUILDROOT_CLEANUP
  - GitHub API rate-limit is avoided by using archive tarball URLs, not the API
  - SourceForge redirects are followed by wget, not by the script
  - Version-variable substitution uses heuristics; manual overrides in
    the VERSION_OVERRIDES dict are expected over time
  - Packages whose version/source is Kconfig-driven (linux, gcc, uboot via
    $(call qstrip,$(BR2_...))) cannot be resolved by regex parsing; they are
    skipped and counted as "unresolvable", not failures. Full resolution
    would require `make show-info` and is out of scope.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration from tunasync environment
# ---------------------------------------------------------------------------

WORKDIR  = Path(os.environ["TUNASYNC_WORKING_DIR"])
UPSTREAM = os.environ.get("TUNASYNC_UPSTREAM_URL", "http://sources.buildroot.net/")
HOME     = os.environ.get("HOME", "/tmp")

BR_GIT_URL    = os.environ.get("TUNASYNC_BUILDROOT_GIT", "https://github.com/buildroot/buildroot.git")
BR_GIT_DIR    = Path(HOME) / "buildroot.git"
BR_BRANCH     = os.environ.get("TUNASYNC_BUILDROOT_BRANCH", "master")
MAXDELETE     = int(os.environ.get("TUNASYNC_BUILDROOT_MAXDELETE", "10000"))
JOBS          = int(os.environ.get("TUNASYNC_BUILDROOT_JOBS", "1"))
DRYRUN        = os.environ.get("TUNASYNC_BUILDROOT_DRYRUN", "") in ("1", "true", "yes")
CLEANUP       = os.environ.get("TUNASYNC_BUILDROOT_CLEANUP", "") in ("1", "true", "yes")
# Per-file download cap; wget's own --timeout keeps idle stalls bounded.
WGET_TIMEOUT  = int(os.environ.get("TUNASYNC_BUILDROOT_WGET_TIMEOUT", "3600"))
HTTP_PROXY    = os.environ.get("https_proxy", os.environ.get("http_proxy", ""))
LOG_FILE      = WORKDIR / ".buildroot-sync.log"
STATE_FILE    = WORKDIR / ".buildroot-sync.state"

# Global statistics. Updated under stats_lock when JOBS > 1.
stats = {"total": 0, "skipped": 0, "downloaded": 0, "failed": 0,
         "deleted": 0, "unresolvable": 0}
stats_lock = threading.Lock()


def bump(key: str, n: int = 1) -> None:
    with stats_lock:
        stats[key] += n


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        # The log lives in the published directory; keep it bounded.
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 4 << 20:
            with LOG_FILE.open("rb") as f:
                f.seek(-(1 << 20), os.SEEK_END)
                tail = f.read()
            LOG_FILE.write_bytes(b"... (older log truncated) ...\n" + tail)
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, **kw)


def remote_size(url: str) -> int | None:
    """HEAD the URL and return Content-Length, or None when unknown.

    Any failure (HEAD rejected, timeout, no Content-Length) yields None,
    which callers must treat as "unknown", never as a mismatch.
    """
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "buildroot-sync"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            cl = resp.headers.get("Content-Length")
            return int(cl) if cl and cl.isdigit() else None
    except Exception:
        return None


def wget(url: str, dest: Path) -> bool:
    """Download a file via wget. Always cleans up the .tmp file on failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.unlink(missing_ok=True)
    cmd = ["wget", "-q", "--timeout=60", "--tries=3", "-O", str(tmp)]
    if HTTP_PROXY:
        cmd[1:1] = ["-e", "use_proxy=on", "-e", f"https_proxy={HTTP_PROXY}"]
    cmd.append(url)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=WGET_TIMEOUT)
    except Exception as e:
        log(f"  wget exception for {url}: {e}")
        tmp.unlink(missing_ok=True)
        return False
    try:
        if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            err = (proc.stderr or "").strip()
            log(f"  wget failed for {url} (rc={proc.returncode}): {err[-300:]}")
            return False
        os.replace(tmp, dest)
        return True
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Package URL extraction from buildroot .mk files
# ---------------------------------------------------------------------------

_GITHUB_RE = re.compile(
    r'^\$\(call\s+github,(?P<org>[^,)]+),(?P<repo>[^,)]+),(?P<version>[^,)]+)\)$'
)
_GITLAB_RE = re.compile(
    r'^\$\(call\s+gitlab,(?P<org>[^,)]+),(?P<repo>[^,)]+),(?P<version>[^,)]+)\)$'
)
# $(call sourceforge,<project>,<file>[,<version>]) -> downloads.sourceforge.net
_SOURCEFORGE_RE = re.compile(
    r'^\$\(call\s+sourceforge,(?P<project>[^,)]+),(?P<file>[^,)]+)'
    r'(?:,(?P<version>[^,)]+))?\)$'
)

# Match VERSION/SITE/SOURCE assignments. Buildroot uses `=`, `?=`, `+=`, and
# also `:=` (immediate assignment) in some packages, all of which we accept.
_ASSIGN_RE = re.compile(
    r'^([A-Za-z0-9_]+)\s*([:+?]?=)\s*(.+?)(?:\s*#.*)?$'
)
_EVAL_RE = re.compile(r'^\$\(eval\s+\$\(([a-z0-9-]+)\)\)$')

VERSION_OVERRIDES: dict[str, str] = {}

# Mirrors normally set via Kconfig; seed with Buildroot's Config.in defaults
# so sites using $(BR2_GNU_MIRROR) / $(BR2_KERNEL_MIRROR) etc. resolve.
GLOBAL_VARIABLES = {
    "BR2_GNU_MIRROR": "https://ftpmirror.gnu.org",
    "BR2_KERNEL_MIRROR": "https://cdn.kernel.org/pub",
    "BR2_LUAROCKS_MIRROR": "http://rocks.moonscript.org",
    "BR2_CPAN_MIRROR": "https://cpan.metacpan.org",
}

# pkg_source_ext (package/pkg-utils.mk): the backup-site tarball of a
# VCS-fetched or post-processed package is <rawname>-<version><suffix>.tar.gz.
_FMT_SUFFIX = {"git": "-git4", "svn": "-svn5", "go": "-go2", "cargo": "-cargo6"}
# $(eval $(cargo-package)) / $(eval $(golang-package)) imply the post-process.
_EVAL_IMPLIES_DPP = {"cargo-package": "cargo", "golang-package": "go"}
# SITE_METHODs whose site is a VCS repo that wget cannot fetch as a tarball;
# only the backup site carries those files.
_VCS_METHODS = {"git", "svn", "bzr", "hg"}

_SIMPLE_VAR_RE = re.compile(r'^[A-Za-z0-9_]+$')
_INNERMOST_RE = re.compile(r'\$\(([^()]*)\)')


def expand_variable(val: str, variables: dict[str, str]) -> str:
    """Iteratively expand innermost $(...) expressions.

    Handles simple $(VAR) references and the $(subst from,to,text) Make
    function. Unknown variables (e.g. Kconfig $(BR2_...)) and unhandled
    functions ($(call ...)) are left untouched for the caller to resolve or
    skip.
    """
    if not val or "$(" not in val:
        return val
    for _ in range(20):
        changed = False
        out = []
        pos = 0
        for m in _INNERMOST_RE.finditer(val):
            inner = m.group(1)
            if inner.startswith("subst "):
                parts = inner[6:].split(",", 2)
                repl = parts[2].replace(parts[0], parts[1]) if len(parts) == 3 else None
            elif _SIMPLE_VAR_RE.match(inner):
                repl = variables.get(inner)
            else:
                repl = None
            if repl is None:
                continue
            out.append(val[pos:m.start()])
            out.append(repl)
            pos = m.end()
            changed = True
        if not changed:
            break
        val = "".join(out) + val[pos:]
    return val


def emit_github(repo_org: str, repo_name: str, version: str) -> str:
    """Return the github archive base URL, matching Buildroot's `github` helper.

    Buildroot defines the site as .../archive/<ref> and downloads
    <site>/<source>; keep the same split so sync_package() appends the actual
    source filename.
    """
    return f"https://github.com/{repo_org}/{repo_name}/archive/{version}"


def emit_gitlab(repo_org: str, repo_name: str, version: str) -> str:
    """Return the gitlab archive base URL, matching Buildroot's `gitlab` helper."""
    return f"https://gitlab.com/{repo_org}/{repo_name}/-/archive/{version}"


def emit_sourceforge(project: str, file: str, version: str = "") -> str:
    """Expand $(call sourceforge,<project>,<file>[,<version>]) to a direct URL."""
    path = file.strip()
    if version:
        path = f"{path}-{version.strip()}"
    return f"https://downloads.sourceforge.net/project/{project.strip()}/{path}"


# File extensions buildroot sources typically carry; used to decide whether a
# URL path already ends in a filename (as opposed to a directory or a bare
# version ref such as ".../archive/1.0").
_ARCHIVE_EXT_RE = re.compile(
    r'\.(?:tar\.(?:gz|xz|bz2|zst|lz|lz4)|tgz|txz|tbz2?|zip|gz|xz|bz2|7z|'
    r'jar|war|deb|rpm|run|bin|iso|img)$', re.IGNORECASE)


def url_has_filename(url: str) -> bool:
    """True if the URL path already ends with a filename, not a directory."""
    last = os.path.basename(urllib.parse.urlparse(url).path)
    return bool(_ARCHIVE_EXT_RE.search(last))


def extract_packages(git_dir: Path) -> list[dict]:
    """Walk buildroot git tree and return list of {name, version, url, source}."""
    mk_files: list[Path] = []
    for subdir in ["boot", "linux", "package", "toolchain", "utils"]:
        d = git_dir / subdir
        if d.is_dir():
            mk_files.extend(sorted(d.rglob("*.mk")))

    log(f"Scanning {len(mk_files)} .mk files for package metadata...")

    # Pass 1: collect per-file raw variables, plus a global fallback map so
    # cross-file references (e.g. QT6BASE_VERSION = $(QT6_VERSION)) resolve.
    global_vars: dict[str, str] = dict(GLOBAL_VARIABLES)
    parsed_files = []
    for mkf in mk_files:
        try:
            text = mkf.read_text(errors="replace")
        except Exception:
            continue
        variables: dict[str, str] = {}
        alt_sources: list[str] = []
        implied_dpp = ""
        upper = mkf.stem.upper().replace("-", "_")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            em = _EVAL_RE.match(stripped)
            if em and em.group(1) in _EVAL_IMPLIES_DPP:
                implied_dpp = _EVAL_IMPLIES_DPP[em.group(1)]
                continue
            m = _ASSIGN_RE.match(stripped)
            if not m:
                continue
            key, op, value = m.group(1), m.group(2), m.group(3).strip()
            if key == f"{upper}_SOURCE" and key in variables and variables[key] != value:
                # Conditional sources (ifeq blocks): keep every variant so
                # per-arch archives (e.g. wf111) are all mirrored.
                alt_sources.append(variables[key])
            if op == "+=":
                variables[key] = (variables.get(key, "") + " " + value).strip()
                global_vars[key] = (global_vars.get(key, "") + " " + value).strip()
            elif op == "?=":
                variables.setdefault(key, value)
                global_vars.setdefault(key, value)
            else:
                variables[key] = value
                global_vars[key] = value
        parsed_files.append((mkf, variables, alt_sources, implied_dpp))

    packages = []
    for mkf, file_vars, alt_sources, implied_dpp in parsed_files:
        stem = mkf.stem
        if not stem or stem in ("pkg", "package", "common"):
            continue
        name = stem
        upper = name.upper().replace("-", "_")
        # Per-file assignments win over the global fallback map.
        variables = {**global_vars, **file_vars}

        version = None
        for prefix in (f"{upper}_VERSION", f"{upper}_REV", f"{upper}_VER"):
            if prefix in variables:
                version = expand_variable(variables[prefix], variables)
                break

        site = None
        for prefix in (f"{upper}_SITE", f"{upper}_URL", f"{upper}_REPO", f"{upper}_MIRROR"):
            if prefix in variables:
                site = expand_variable(variables[prefix], variables)
                break

        source = None
        for prefix in (f"{upper}_SOURCE", f"{upper}_DL_FILE", f"{upper}_TARBALL"):
            if prefix in variables:
                source = expand_variable(variables[prefix], variables)
                break

        if not name or not version:
            continue

        # Default SOURCE (package/pkg-utils.mk pkg_source_ext):
        # <rawname>-<version><site-method/post-process suffix>.tar.gz
        site_method = variables.get(f"{upper}_SITE_METHOD", "")
        dpp = variables.get(f"{upper}_DOWNLOAD_POST_PROCESS", "") or implied_dpp
        fmt_suffix = _FMT_SUFFIX.get(site_method, "") + _FMT_SUFFIX.get(dpp, "")
        if not source:
            source = f"{name}-{version}{fmt_suffix}.tar.gz"

        pkg_url = None
        guess = False
        if not site:
            guess = True
        else:
            m = _GITHUB_RE.match(site)
            if m:
                # The third macro argument is the archive ref (which may carry
                # a prefix, e.g. v$(FOO_VERSION)) -- pass it, not the bare
                # package version.
                pkg_url = emit_github(m.group("org").strip(),
                                      m.group("repo").strip(),
                                      m.group("version").strip())
            else:
                m = _GITLAB_RE.match(site)
                if m:
                    pkg_url = emit_gitlab(m.group("org").strip(),
                                          m.group("repo").strip(),
                                          m.group("version").strip())
                else:
                    m = _SOURCEFORGE_RE.match(site)
                    if m:
                        pkg_url = emit_sourceforge(m.group("project"),
                                                   m.group("file"),
                                                   m.group("version") or "")
                    elif site_method in _VCS_METHODS:
                        # VCS repo URL: wget cannot fetch it; only the backup
                        # site carries the <fmt-suffixed> tarball.
                        pkg_url = None
                    else:
                        cleaned = re.sub(r'\$\([^)]+\)', '', site).rstrip('/')
                        if cleaned and cleaned.startswith(("http://", "https://",
                                                           "ftp://")):
                            pkg_url = cleaned

        entry = {"name": name, "version": version, "url": pkg_url,
                 "source": source}
        if guess:
            entry["guess"] = True
        packages.append(entry)

        # Mirror every conditional SOURCE variant (same site/version).
        for alt in alt_sources:
            alt_src = expand_variable(alt, variables)
            if alt_src and alt_src != source and "$(" not in alt_src:
                packages.append({"name": name, "version": version,
                                 "url": pkg_url, "source": alt_src})

    log(f"Extracted {len(packages)} package candidates with URLs")
    guess_count = sum(1 for p in packages if p.get("guess"))
    log(f"  ({guess_count} packages without explicit SITE -- will try backup site)")
    return packages


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def sync_package(pkg: dict) -> bool:
    """Download one package file if not already present. Counts toward stats."""
    bump("total")

    name = pkg["name"]
    url = pkg.get("url")
    version = pkg["version"]
    source = pkg.get("source", "")

    if source:
        local_file = source
    elif url and url_has_filename(url):
        local_file = os.path.basename(urllib.parse.urlparse(url).path)
    else:
        local_file = f"{name}-{version}.tar.gz"

    # Unexpanded Make variables (e.g. $(call qstrip,$(BR2_...)) in Kconfig-
    # driven packages such as linux/gcc/uboot) cannot be resolved by this
    # regex parser. They are skipped and counted as "unresolvable" rather
    # than failures: they need `make show-info`/Kconfig evaluation, which is
    # out of scope here, and they must not make every run exit non-zero.
    if "$(" in local_file or "${" in local_file:
        log(f"  {name}: unresolvable filename (Kconfig-driven?): {local_file}")
        bump("unresolvable")
        return True

    dest = WORKDIR / name / local_file

    # The backup site (TUNASYNC_UPSTREAM_URL) is canonical for a mirror of
    # sources.buildroot.net and is tried FIRST; the package's own upstream
    # site is only the fallback. This also reduces load on upstream projects.
    urls_to_try = [f"{UPSTREAM.rstrip('/')}/{name}/{local_file}"]
    if url:
        if url_has_filename(url):
            # The URL already ends in a filename -- use it as-is.
            urls_to_try.append(url)
        else:
            # Directory-style site (including github/gitlab archive bases):
            # append the actual source filename, as Buildroot's helpers do.
            urls_to_try.append(url.rstrip("/") + "/" + local_file)

    if dest.exists() and dest.stat().st_size > 0:
        # Compare Content-Length before skipping: if upstream republished or
        # corrected the file under the same name, re-download it. An unknown
        # remote size (HEAD rejected / no Content-Length) keeps the local file.
        local_size = dest.stat().st_size
        remote = remote_size(urls_to_try[0])
        if remote is None or remote == local_size:
            bump("skipped")
            return True
        log(f"  {name}: size mismatch (local={local_size}, remote={remote}); re-downloading")

    for try_url in urls_to_try:
        if DRYRUN:
            log(f"  [DRYRUN] {name}: {try_url}")
            return True
        log(f"  {name}: {try_url}")
        if wget(try_url, dest):
            bump("downloaded")
            return True
        # wget() only ever replaces dest on success; on failure the previous
        # known-good file must stay in place (only the .tmp is removed).

    bump("failed")
    return False


def clean_stale_files(packages: list[dict]) -> None:
    """Optionally remove local files that no package now references.

    Only runs when TUNASYNC_BUILDROOT_CLEANUP is enabled, and refuses to
    remove more than MAXDELETE files in a single run.
    """
    if not CLEANUP:
        log("Cleanup: skipped (set TUNASYNC_BUILDROOT_CLEANUP=1 to enable)")
        return

    if not packages:
        # Safety fuse: with an empty package list every local file looks stale.
        log("Cleanup: refusing to run, extraction yielded 0 packages")
        return

    expected: set[Path] = set()
    for pkg in packages:
        name = pkg["name"]
        source = pkg.get("source") or ""
        url = pkg.get("url") or ""
        if source:
            expected.add(WORKDIR / name / source)
        elif url and url_has_filename(url):
            expected.add(WORKDIR / name / os.path.basename(urllib.parse.urlparse(url).path))

    stale = []
    for pkg_dir in WORKDIR.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name.startswith("."):
            continue
        for f in pkg_dir.iterdir():
            if not f.is_file():
                continue
            if f in expected:
                continue
            stale.append(f)

    if len(stale) > MAXDELETE:
        log(f"Cleanup: refusing to delete {len(stale)} files "
            f"(exceeds TUNASYNC_BUILDROOT_MAXDELETE={MAXDELETE})")
        return

    for f in stale:
        try:
            f.unlink()
            bump("deleted")
        except OSError as e:
            log(f"Cleanup: failed to remove {f}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("=== buildroot-sync started ===")
    log(f"Work directory: {WORKDIR}")
    log(f"Git URL: {BR_GIT_URL}  Branch: {BR_BRANCH}")
    log(f"Max delete: {MAXDELETE}  Jobs: {JOBS}  Dry run: {DRYRUN}  Cleanup: {CLEANUP}")
    WORKDIR.mkdir(parents=True, exist_ok=True)

    log("Step 1: Fetching buildroot git tree...")
    git_ok = False
    try:
        if (BR_GIT_DIR / ".git").exists():
            r = run(["git", "-C", str(BR_GIT_DIR), "fetch", "--depth=1", "origin", BR_BRANCH])
            if r.returncode != 0:
                log(f"git fetch failed (rc={r.returncode}): {r.stderr.strip()}")
            else:
                r = run(["git", "-C", str(BR_GIT_DIR), "reset", "--hard", f"origin/{BR_BRANCH}"])
                if r.returncode != 0:
                    log(f"git reset failed (rc={r.returncode}): {r.stderr.strip()}")
                else:
                    git_ok = True
        else:
            r = run(["git", "clone", "--depth=1", "--branch", BR_BRANCH,
                     BR_GIT_URL, str(BR_GIT_DIR)])
            if r.returncode != 0:
                log(f"git clone failed (rc={r.returncode}): {r.stderr.strip()}")
            else:
                git_ok = True
    except subprocess.TimeoutExpired as e:
        log(f"git operation timed out: {e}")

    if not git_ok:
        log("Git tree unavailable; aborting (no package list to sync).")
        return 1

    head = subprocess.check_output(
        ["git", "-C", str(BR_GIT_DIR), "rev-parse", "HEAD"], text=True
    ).strip()[:8]

    last_head = ""
    if STATE_FILE.exists():
        last_head = STATE_FILE.read_text().strip()
    # An unchanged HEAD only means "no upstream movement"; still run the full
    # verification pass so files deleted or corrupted since the last run are
    # reconciled, and a previous failed run is not hidden by the state file.
    if last_head == head:
        log(f"No new commits since {head}; running full verification pass")
    else:
        log(f"Current HEAD: {head}  (last: {last_head or 'none'})")

    log("Step 2: Extracting package download URLs...")
    packages = extract_packages(BR_GIT_DIR)
    log(f"Found {len(packages)} packages to process")
    if not packages:
        log("Extraction yielded 0 packages (parser/tree problem?); aborting "
            "without touching state or local files.")
        return 1

    log("Step 3: Downloading new/changed files...")
    if JOBS > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=JOBS) as ex:
            futures = [ex.submit(sync_package, p) for p in packages]
            for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
                try:
                    fut.result()
                except Exception as e:
                    # A crashed worker means a package was not synchronized;
                    # count it so the state file is not advanced.
                    bump("failed")
                    log(f"  unexpected error: {e}")
                if i % 500 == 0:
                    with stats_lock:
                        snap = dict(stats)
                    log(f"  Progress: {snap['total']}/{len(packages)} -- "
                        f"skipped={snap['skipped']} "
                        f"downloaded={snap['downloaded']} "
                        f"failed={snap['failed']}")
    else:
        for pkg in packages:
            sync_package(pkg)
            if stats["total"] % 500 == 0:
                log(f"  Progress: {stats['total']}/{len(packages)} -- "
                    f"skipped={stats['skipped']} "
                    f"downloaded={stats['downloaded']} "
                    f"failed={stats['failed']}")

    # Cleanup is skipped on incomplete runs: a failed download must never
    # delete the package's previously mirrored files.
    if DRYRUN or stats["failed"] > 0:
        log("Cleanup: skipped (dry run or failed downloads)")
    else:
        clean_stale_files(packages)

    # Only advance the state after a real, fully successful run; otherwise the
    # next run would skip this commit and never retry the failed downloads.
    if DRYRUN:
        log("Dry run: not writing state file")
    elif stats["failed"] > 0:
        log(f"Not advancing state ({stats['failed']} failure(s)); next run will retry")
    else:
        STATE_FILE.write_text(head)

    log("=== buildroot-sync finished ===")
    log(f"Summary: total={stats['total']} skipped={stats['skipped']} "
        f"downloaded={stats['downloaded']} failed={stats['failed']} "
        f"unresolvable={stats['unresolvable']} deleted={stats['deleted']}")
    return 0 if stats["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
