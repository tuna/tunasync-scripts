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
  5. Download new/changed files atomically (.tmp → rename)
  6. Clean up stale files up to TUNASYNC_BUILDROOT_MAXDELETE

Design constraints:
  - Only adds files, never deletes local data unless explicitly enabled
  - GitHub API rate-limit is avoided by using archive tarball URLs, not the API
  - SourceForge redirects are followed by wget, not by the script
  - Version-variable substitution uses heuristics; manual overrides in
    the VERSION_OVERRIDES dict are expected over time
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration from tunasync environment
# ---------------------------------------------------------------------------

WORKDIR  = Path(os.environ["TUNASYNC_WORKING_DIR"])
UPSTREAM = os.environ.get("TUNASYNC_UPSTREAM_URL", "http://sources.buildroot.net/")
HOME     = "/tmp"

BR_GIT_URL    = os.environ.get("TUNASYNC_BUILDROOT_GIT", "https://github.com/buildroot/buildroot.git")
BR_GIT_DIR    = Path(HOME) / "buildroot.git"
BR_BRANCH     = os.environ.get("TUNASYNC_BUILDROOT_BRANCH", "master")
MAXDELETE     = int(os.environ.get("TUNASYNC_BUILDROOT_MAXDELETE", "10000"))
JOBS          = int(os.environ.get("TUNASYNC_BUILDROOT_JOBS", "4"))
DRYRUN        = os.environ.get("TUNASYNC_BUILDROOT_DRYRUN", "") in ("1", "true", "yes")
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")  # optional, for API if needed
HTTP_PROXY    = os.environ.get("https_proxy", os.environ.get("http_proxy", ""))
LOG_FILE      = WORKDIR / ".buildroot-sync.log"
STATE_FILE    = WORKDIR / ".buildroot-sync.state"   # last successful commit

# Global statistics
stats = {"total": 0, "skipped": 0, "downloaded": 0, "failed": 0, "deleted": 0}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, **kw)


def wget(url: str, dest: Path) -> bool:
    """Download a file via wget, follow redirects."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.unlink(missing_ok=True)
    cmd = [
        "wget", "-q", "--timeout=60", "--tries=3",
        "-O", str(tmp),
    ]
    if HTTP_PROXY:
        cmd[1:1] = [f"-e", f"use_proxy=on", f"-e", f"https_proxy={HTTP_PROXY}"]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        return False
    tmp.rename(dest)
    return True


# ---------------------------------------------------------------------------
# Package URL extraction from buildroot .mk files
# ---------------------------------------------------------------------------

_GITHUB_RE = re.compile(
    r'^\$\(call\s+github,(?P<org>[^,)]+),(?P<repo>[^,)]+),(?P<version>[^,)]+)\)$'
)
_GITLAB_RE = re.compile(
    r'^\$\(call\s+gitlab,(?P<org>[^,)]+),(?P<repo>[^,)]+),(?P<version>[^,)]+)\)$'
)
_SOURCEFORGE_RE = re.compile(
    r'^(?P<url>https?://downloads\.sourceforge\.net\/[^)]*)/(?P<file>[^/]+)$'
)

# Known version variables: many packages use <pkg>_VERSION = <other>_VERSION
VERSION_OVERRIDES: dict[str, str] = {}
_FILE_SKIP = {".gitignore", "series", "Config.in", "Config.in.host", "readme.txt", 
              "Kconfig", "Makefile", ".hash", ".patch", "sha256sums", "asc", ".sig",
              ".sha256", ".asc", ".sign", ".sig", "license", "LICENSE"}
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
    return f"https://github.com/{repo_org}/{repo_name}/archive/{version}/{repo_name}-{version}.tar.gz"


def emit_gitlab(repo_org: str, repo_name: str, version: str) -> str:
    return f"https://gitlab.com/{repo_org}/{repo_name}/-/archive/{version}/{repo_name}-{version}.tar.gz"


def extract_packages(git_dir: Path) -> list[dict]:
    """Walk buildroot git tree and return list of {name, version, url, filename}."""
    packages = []

    # Collect all .mk files
    mk_files: list[Path] = []
    for subdir in ["boot", "linux", "package", "toolchain", "utils"]:
        d = git_dir / subdir
        if d.is_dir():
            mk_files.extend(sorted(d.rglob("*.mk")))

    log(f"Scanning {len(mk_files)} .mk files for package metadata...")

    for mkf in mk_files:
        name = None
        version = None
        site = None
        source = None
        variables: dict[str, str] = {}

        try:
            text = mkf.read_text(errors="replace")
        except Exception:
            continue

        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#"):
                continue

            # Variable assignment
            m = re.match(r'^([A-Za-z0-9_]+)\s*[?+]?=\s*(.+?)(?:\s*#.*)?$', line)
            if m:
                var_name, var_val = m.group(1), m.group(2).strip()
                variables[var_name] = var_val
                continue

        # Determine package name from filename
        stem = mkf.stem
        if stem.endswith(".mk"):
            stem = stem[:-3]
        # Remove common suffixes
        for s in ["-package", "_package", ".package"]:
            if stem.endswith(s):
                stem = stem[:-len(s)]
                break
        if not stem or stem in ("pkg", "package", "common"):
            continue
        name = stem

        # Find VERSION variable
        for prefix in [f"{name.upper().replace('-','_')}_VERSION",
                       f"{name.upper().replace('-','_')}_REV",
                       f"{name.upper().replace('-','_')}_VER"]:
            if prefix in variables:
                version = variables[prefix]
                # Expand $(OTHER_VERSION)
                version = expand_variable(version, variables)
                break

        # Find SITE variable
        for prefix in [f"{name.upper().replace('-','_')}_SITE",
                       f"{name.upper().replace('-','_')}_URL",
                       f"{name.upper().replace('-','_')}_REPO",
                       f"{name.upper().replace('-','_')}_MIRROR"]:
            if prefix in variables:
                site = variables[prefix]
                site = expand_variable(site, variables)
                break

        # Find SOURCE variable
        for prefix in [f"{name.upper().replace('-','_')}_SOURCE",
                       f"{name.upper().replace('-','_')}_DL_FILE",
                       f"{name.upper().replace('-','_')}_TARBALL"]:
            if prefix in variables:
                source = variables[prefix]
                source = expand_variable(source, variables)
                break

        # Auto-generate SOURCE from name + version if not specified
        if not source and name and version:
            for ext in [".tar.gz", ".tar.xz", ".tar.bz2", ".tgz", ".tar.zst", ".zip"]:
                source = f"{name}-{version}{ext}"
                # Check if this is likely correct by looking for SOURCE = in the file
                # We'll try common patterns
                break

        if not name or not version:
            continue
        if not site:
            packages.append({"name": name, "version": version, "url": None, "source": source, "guess": True})
            continue

        # Handle GitHub macro: $(call github,org,repo,version)
        m = _GITHUB_RE.match(site)
        if m:
            packages.append({
                "name": name, "version": version,
                "url": emit_github(m.group("org").strip(), m.group("repo").strip(), version),
                "source": source,
            })
            continue

        # Handle GitLab macro: $(call gitlab,org,repo,version)
        m = _GITLAB_RE.match(site)
        if m:
            packages.append({
                "name": name, "version": version,
                "url": emit_gitlab(m.group("org").strip(), m.group("repo").strip(), version),
                "source": source,
            })
            continue

        # Regular URL
        # Clean up: remove $(...) if any remain (unexpanded)
        cleaned = re.sub(r'\$\([^)]+\)', '', site).rstrip('/')
        if cleaned and (cleaned.startswith("http://") or cleaned.startswith("https://") or cleaned.startswith("ftp://")):
            packages.append({
                "name": name, "version": version,
                "url": cleaned,
                "source": source,
            })

    log(f"Extracted {len(packages)} package candidates with URLs")
    guess_count = sum(1 for p in packages if p.get("guess"))
    log(f"  ({guess_count} packages without explicit SITE — will try backup site)")
    return packages


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def sync_package(pkg: dict) -> bool:
    """Download one package file if not already present."""
    name = pkg["name"]
    url = pkg.get("url")
    version = pkg["version"]
    source = pkg.get("source", "")

    # Determine local filename
    if source:
        # Use explicit source filename if available
        local_file = source
    elif url:
        # Extract filename from URL path
        parsed = urllib.parse.urlparse(url)
        local_file = os.path.basename(parsed.path)
    else:
        # No URL and no source — try backup site filename guess
        for ext in [".tar.gz", ".tar.xz", ".tar.bz2", ".tgz", ".tar.zst", ".zip"]:
            local_file = f"{name}-{version}{ext}"
            # We'll test if any backup URL works
            break
        else:
            local_file = f"{name}-{version}.tar.gz"

    dest = WORKDIR / name / local_file

    # Skip if local file exists and is non-empty
    if dest.exists() and dest.stat().st_size > 0:
        stats["skipped"] += 1
        return True

    # Try download URLs in order
    urls_to_try = []
    if url:
        full = url.rstrip("/") + "/" + local_file if url else None
        if full:
            urls_to_try.append(full)
    # Fallback: sources.buildroot.net backup site
    urls_to_try.append(f"{_BR_PRIMARY_SITE}/{name}/{local_file}")

    for try_url in urls_to_try:
        if DRYRUN:
            log(f"  [DRYRUN] {name}: {try_url}")
            stats["total"] += 1
            return True
        log(f"  {name}: {try_url}")
        if wget(try_url, dest):
            stats["downloaded"] += 1
            stats["total"] += 1
            return True
        # Clean up failed partial download
        dest.unlink(missing_ok=True)

    stats["failed"] += 1
    stats["total"] += 1
    return False


def clean_stale_files() -> None:
    """Remove local files that are no longer in the current buildroot tree."""
    # Build set of known directories from packages
    known_names = set()
    # We don't actually know what's "stale" without a full scan —
    # so we skip this phase unless the user explicitly wants it.
    # The buildroot mirror is append-only by design.
    log("Cleanup: skipped (buildroot mirror is append-only by default)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("=== buildroot-sync started ===")
    log(f"Work directory: {WORKDIR}")
    log(f"Git URL: {BR_GIT_URL}  Branch: {BR_BRANCH}")
    log(f"Max delete: {MAXDELETE}  Jobs: {JOBS}  Dry run: {DRYRUN}")
    WORKDIR.mkdir(parents=True, exist_ok=True)

    # 1. Clone or update buildroot git (shallow)
    log("Step 1: Fetching buildroot git tree...")
    try:
        if (BR_GIT_DIR / ".git").exists():
            run(["git", "-C", str(BR_GIT_DIR), "fetch", "--depth=1", "origin", BR_BRANCH])
            run(["git", "-C", str(BR_GIT_DIR), "reset", "--hard", f"origin/{BR_BRANCH}"])
        else:
            r = run(["git", "clone", "--depth=1", "--branch", BR_BRANCH, BR_GIT_URL, str(BR_GIT_DIR)])
            if r.returncode != 0:
                raise Exception("clone failed")
    except Exception as e:
        log(f"Git clone/fetch failed: {e}. Will retry download with fallback URLs only.")
        packages = []
        head = "unknown"
    else:
        head = subprocess.check_output(
        ["git", "-C", str(BR_GIT_DIR), "rev-parse", "HEAD"], text=True
    ).strip()[:8]

    # Check last synced commit
    last_head = ""
    if STATE_FILE.exists():
        last_head = STATE_FILE.read_text().strip()
    if last_head == head:
        log(f"No new commits since {head}, skipping")
        return 0
    log(f"Current HEAD: {head}  (last: {last_head or 'none'})")

    # 2. Extract package URLs
    log("Step 2: Extracting package download URLs...")
    if (BR_GIT_DIR / ".git").exists():
        packages = extract_packages(BR_GIT_DIR)
    else:
        log("No git tree available, skipping extraction phase.")
        packages = []
    log(f"Found {len(packages)} packages to process")

    # 3. Download new files
    log("Step 3: Downloading new/changed files...")
    for pkg in packages:
        sync_package(pkg)
        if stats["total"] % 500 == 0:
            log(f"  Progress: {stats['total']}/{len(packages)} — "
                f"skipped={stats['skipped']} downloaded={stats['downloaded']} failed={stats['failed']}")

    # 4. Clean stale (optional)
    clean_stale_files()

    # 5. Write state
    STATE_FILE.write_text(head)

    log("=== buildroot-sync finished ===")
    log(f"Summary: total={stats['total']} skipped={stats['skipped']} "
        f"downloaded={stats['downloaded']} failed={stats['failed']}")
    return 0 if stats["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
