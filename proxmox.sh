#!/bin/bash
set -euo pipefail

# Backward-compatible entry point for the Proxmox mirror.
#
# The mirror is synced by two stages with different runtime requirements:
#   proxmox-deb-img.sh  /debian/ + /images/ via tsumugu (needs tsumugu)
#   proxmox-iso.py      /iso/ custom-page scraper       (needs python3)
# No stock image ships both, so the documented deployment is two tunasync
# jobs — one per image — sharing the same working directory, with each job
# invoking its stage script directly (see the PR #206 description for a
# config example).
#
# This wrapper keeps legacy single-job setups that invoke proxmox.sh
# working: it runs every stage the current image supports, prints a loud
# warning for each stage it has to skip, and exits non-zero when no stage
# can run at all.

_here=$(dirname "$(realpath "$0")")

: "${TUNASYNC_WORKING_DIR:?TUNASYNC_WORKING_DIR is required (tunasync sets it for every job)}"

have_deb=1
have_iso=1
if ! command -v tsumugu >/dev/null 2>&1 || [ ! -f "${_here}/proxmox-deb-img.sh" ]; then
  have_deb=0
fi
if ! command -v python3 >/dev/null 2>&1 || [ ! -f "${_here}/proxmox-iso.py" ]; then
  have_iso=0
fi

if [ "$have_deb" -eq 0 ] && [ "$have_iso" -eq 0 ]; then
  echo "proxmox.sh: error: no stage can run in this image (need tsumugu +" >&2
  echo "proxmox.sh: proxmox-deb-img.sh for /debian+/images, or python3 +" >&2
  echo "proxmox.sh: proxmox-iso.py for /iso); nothing synced." >&2
  exit 1
fi
if [ "$have_deb" -eq 0 ]; then
  echo "proxmox.sh: warning: tsumugu/proxmox-deb-img.sh unavailable; skipping" >&2
  echo "proxmox.sh: the /debian + /images stage. Run it as its own tunasync job" >&2
  echo "proxmox.sh: from the tsumugu image (see PR #206 description)." >&2
fi
if [ "$have_iso" -eq 0 ]; then
  echo "proxmox.sh: warning: python3/proxmox-iso.py unavailable; skipping the" >&2
  echo "proxmox.sh: /iso stage. Run it as its own tunasync job from the" >&2
  echo "proxmox.sh: tunasync-scripts image (see PR #206 description)." >&2
fi

if [ "$have_deb" -eq 1 ]; then
  "${_here}/proxmox-deb-img.sh"
fi
if [ "$have_iso" -eq 1 ]; then
  python3 "${_here}/proxmox-iso.py"
fi
