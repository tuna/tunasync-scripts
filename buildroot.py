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
  3. Expand version variables and macro calls (github, gitlab, sourceforge)
  4. Compare each candidate URL against the local mirror
  5. Download new/changed files atomically (.tmp -> rename)
  6. Optional cleanup of stale files up to TUNASYNC_BUILDROOT_MAXDELETE

Design constraints:
  - Only adds files; cleanup is opt-in via TUNASYNC_BUILDROOT_CLEANUP
  - GitHub API rate-limit is avoided by using archive tarball URLs, not the API
  - SourceForge redirects are followed by wget, not by the script
  - Version-variable substitution uses heuristics; manual overrides in
    the VERSION_OVERRIDES dict are expected over time
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import os
import re
import subprocess
import sys
import time
import urllib.parse
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
HTTP_PROXY    = os.environ.get("https_proxy", os.environ.get("http_proxy", ""))
LOG_FILE      = WORKDIR / ".buildroot-sync.log"
STATE_FILE    = WORKDIR / ".buildroot-sync.state"

# Global statistics. Updated under stats_lock when JOBS > 1.
stats = {"total": 0, "skipped": 0, "downloaded": 0, "failed": 0, "deleted": 0}
import threading
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
        proc = subprocess.run(cmd, capture_output=True, timeout=300)
    except Exception:
        tmp.unlink(missing_ok=True)
        return False
    try:
        if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
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

# Match VERSION/SITE/SOURCE assignments. Buildroot uses `=`, `?=`, `+=`, and
# also `:=` (immediate assignment) in some packages, all of which we accept.
_ASSIGN_RE = re.compile(
    r'^([A-Za-z0-9_]+)\s*[:?+]?=\s*(.+?)(?:\s*#.*)?$'
)

VERSION_OVERRIDES: dict[str, str] = {}
_BR_PRIMARY_SITE = "https://sources.buildroot.net"


def expand_variable(val: str, variables: dict[str, str]) -> str:
    """Recursively expand $(VAR) references in val."""
    if not val or "$(" not in val:
        return val
    changed = True
    max_iter = 20
    while changed and max_iter > 0:
        changed = False
        max_iter -= 1
        for var, vval in sorted(variables.items(), key=lambda x: -len(x[0])):
            needle = f"$({var})"
            if needle in val:
                val = val.replace(needle, vval)
                changed = True
    return val


def emit_github(repo_org: str, repo_name: str, version: str) -> str:
    """Return the github archive tarball URL ending with the filename."""
    return (f"https://github.com/{repo_org}/{repo_name}"
            f"/archive/{version}/{repo_name}-{version}.tar.gz")


def emit_gitlab(repo_org: str, repo_name: str, version: str) -> str:
    """Return the gitlab archive tarball URL ending with the filename."""
    return (f"https://gitlab.com/{repo_org}/{repo_name}"
            f"/-/archive/{version}/{repo_name}-{version}.tar.gz")


def url_has_filename(url: str) -> bool:
    """True if the URL path already ends with a filename, not a directory."""
    parsed = urllib.parse.urlparse(url)
    last = os.path.basename(parsed.path)
    return bool(last) and "." in last


def extract_packages(git_dir: Path) -> list[dict]:
    """Walk buildroot git tree and return list of {name, version, url, source}."""
    packages = []

    mk_files: list[Path] = []
    for subdir in ["boot", "linux", "package", "toolchain", "utils"]:
        d = git_dir / subdir
        if d.is_dir():
            mk_files.extend(sorted(d.rglob("*.mk")))

    log(f"Scanning {len(mk_files)} .mk files for package metadata...")

    for mkf in mk_files:
        variables: dict[str, str] = {}
        try:
            text = mkf.read_text(errors="replace")
        except Exception:
            continue

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = _ASSIGN_RE.match(stripped)
            if m:
                variables[m.group(1)] = m.group(2).strip()

        stem = mkf.stem
        if not stem or stem in ("pkg", "package", "common"):
            continue
        name = stem
        upper = name.upper().replace("-", "_")

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

        if not source and name and version:
            source = f"{name}-{version}.tar.gz"

        if not name or not version:
            continue
        if not site:
            packages.append({"name": name, "version": version, "url": None,
                             "source": source, "guess": True})
            continue

        m = _GITHUB_RE.match(site)
        if m:
            packages.append({
                "name": name, "version": version,
                "url": emit_github(m.group("org").strip(),
                                   m.group("repo").strip(), version),
                "source": source,
            })
            continue

        m = _GITLAB_RE.match(site)
        if m:
            packages.append({
                "name": name, "version": version,
                "url": emit_gitlab(m.group("org").strip(),
                                   m.group("repo").strip(), version),
                "source": source,
            })
            continue

        cleaned = re.sub(r'\$\([^)]+\)', '', site).rstrip('/')
        if cleaned and (cleaned.startswith("http://") or
                        cleaned.startswith("https://") or
                        cleaned.startswith("ftp://")):
            packages.append({
                "name": name, "version": version,
                "url": cleaned,
                "source": source,
            })

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

    dest = WORKDIR / name / local_file

    if dest.exists() and dest.stat().st_size > 0:
        bump("skipped")
        return True

    urls_to_try = []
    if url:
        if url_has_filename(url):
            # GitHub / GitLab archive URLs already include the filename --
            # do not append local_file again.
            urls_to_try.append(url)
        else:
            urls_to_try.append(url.rstrip("/") + "/" + local_file)
    urls_to_try.append(f"{_BR_PRIMARY_SITE}/{name}/{local_file}")

    for try_url in urls_to_try:
        if DRYRUN:
            log(f"  [DRYRUN] {name}: {try_url}")
            return True
        log(f"  {name}: {try_url}")
        if wget(try_url, dest):
            bump("downloaded")
            return True
        dest.unlink(missing_ok=True)

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

    if not git_ok:
        log("Git tree unavailable; aborting (no package list to sync).")
        return 1

    head = subprocess.check_output(
        ["git", "-C", str(BR_GIT_DIR), "rev-parse", "HEAD"], text=True
    ).strip()[:8]

    last_head = ""
    if STATE_FILE.exists():
        last_head = STATE_FILE.read_text().strip()
    if last_head == head:
        log(f"No new commits since {head}, skipping")
        return 0
    log(f"Current HEAD: {head}  (last: {last_head or 'none'})")

    log("Step 2: Extracting package download URLs...")
    packages = extract_packages(BR_GIT_DIR)
    log(f"Found {len(packages)} packages to process")

    log("Step 3: Downloading new/changed files...")
    if JOBS > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=JOBS) as ex:
            futures = [ex.submit(sync_package, p) for p in packages]
            for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
                try:
                    fut.result()
                except Exception as e:
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

    clean_stale_files(packages)

    STATE_FILE.write_text(head)

    log("=== buildroot-sync finished ===")
    log(f"Summary: total={stats['total']} skipped={stats['skipped']} "
        f"downloaded={stats['downloaded']} failed={stats['failed']} "
        f"deleted={stats['deleted']}")
    return 0 if stats["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
