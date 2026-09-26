#!/bin/bash
set -euo pipefail

# Mirrors the Proxmox Debian repositories (/debian/) and the standalone
# images tree (/images/) with tsumugu. The /iso/ tree is synced by the
# companion proxmox-iso.py, which needs python3 and therefore runs as a
# separate job in a different image; proxmox.sh is a compatibility wrapper
# that runs whichever stages the current image provides. The documented
# deployment is two tunasync jobs sharing one working directory (see PR
# #206 description for a config example).

_here=$(dirname "$(realpath "$0")")

# tsumugu.sh variable conventions, inlined on purpose: production
# bind-mounts only this single script into the tsumugu image, so tsumugu.sh
# itself cannot be sourced or called here. Defaults follow tsumugu.sh
# (required TUNASYNC_WORKING_DIR, threads 2, maxdelete 1000, versioned user
# agent, NO_COLOR).
WORKDIR="${TUNASYNC_WORKING_DIR:?TUNASYNC_WORKING_DIR is required (tunasync sets it for every job)}"
UPSTREAM="${TUNASYNC_UPSTREAM_URL:-http://download.proxmox.com/}"
MAXDELETE="${TUNASYNC_TSUMUGU_MAXDELETE:-1000}"
THREADS="${TUNASYNC_TSUMUGU_THREADS:-2}"
USERAGENT="${TUNASYNC_TSUMUGU_USERAGENT:-"tsumugu/$(tsumugu --version | tail -n1 | cut -d' ' -f2)"}"
export NO_COLOR=1

mkdir -p "$WORKDIR/debian" "$WORKDIR/images"

# Upstream /debian/dists/ is a real directory duplicating the pve packages
# (the pve Packages indices reference dists/... paths). The legacy apt-sync
# based script mirrored it as a `debian/dists -> pve/dists` symlink; create
# the same symlink *before* syncing so fresh installs never download a
# second copy. tsumugu lists the upstream dists/ dir, sees the local
# symlink, records it in its keep-set, and never descends into it.
if [ -L "$WORKDIR/debian/dists" ] || [ ! -e "$WORKDIR/debian/dists" ]; then
  ln -sfn pve/dists "$WORKDIR/debian/dists"
fi

# Scope of the /debian/ sync.
#
# The default (restricted) scope matches the legacy apt-sync based
# proxmox.sh:
#   repos:  pve, pbs, pbs-client, pmg
#   suites: everything upstream publishes for them (currently bullseye,
#           bookworm, trixie — the same set as apt-sync.py's @debian-current)
#   arch:   amd64 only
# plus the top-level files (key.asc, *.gpg). The ceph-*, corosync-3, pdm and
# devel repos and the /dists/ duplicate tree are excluded.
#
# The generic '/binary-arm64/' rule replaces the former suite-specific
# 'dists/trixie/pve-test/binary-arm64' excludes: those trees returned 401
# when listed upstream at the time (they have since been fixed), and the
# legacy scope is amd64-only anyway. A suite-agnostic regex cannot go stale
# when the next Debian release shows up.
#
# Operational warning: tsumugu treats an excluded remote path as absent
# upstream, so matching LOCAL content is removed by its cleanup pass
# (bounded by --max-delete, which aborts the run when exceeded). Tightening
# the scope on an existing full mirror therefore deletes the extra trees;
# try --dry-run via TUNASYNC_TSUMUGU_OPTIONS first.
#
# Set PROXMOX_DEB_ALL=1 to mirror the complete /debian/ tree instead.
common_excludes=(
  # Historical: per-suite changelog files are huge and unused locally.
  --exclude '/devel/dists/.+changelog$'
  --exclude '/pmg/dists/.+changelog$'
)
if [ "${PROXMOX_DEB_ALL:-0}" = "1" ]; then
  scope_args=()
else
  scope_args=(
    # exclusion-v2: the first matching rule in this order decides; unmatched
    # paths would be included, so the trailing catch-all exclude is what
    # actually narrows the scope.
    --exclusion-v2
    --exclude '/binary-arm64/'
    --include '^/$'
    # Let tsumugu see /dists/ so the local debian/dists symlink lands in its
    # keep-set; the symlink itself is never descended into (see above).
    --include '^/dists/'
    --include '^/(pve|pbs|pbs-client|pmg)(/|$)'
    --include '^/[^/]+$'
    --exclude '.*'
  )
fi

# --timezone 0: parse nginx listing timestamps as UTC instead of letting
# tsumugu guess the zone via recursive HEAD probes; the guesser has panicked
# on other mirrors (zabbix-app) and download.proxmox.com listings are UTC.
tsumugu sync \
  --timezone 0 --user-agent "$USERAGENT" --max-delete "$MAXDELETE" \
  --parser nginx --threads "$THREADS" \
  "${common_excludes[@]}" ${scope_args[@]+"${scope_args[@]}"} \
  "${UPSTREAM%/}/debian/" "$WORKDIR/debian"

tsumugu sync \
  --timezone 0 --user-agent "$USERAGENT" --max-delete "$MAXDELETE" \
  --parser nginx --threads "$THREADS" \
  "${UPSTREAM%/}/images/" "$WORKDIR/images"

# Size accounting for the tunasync size report, following the repo
# convention: "+<bytes>" entries in REPO_SIZE_FILE are summed into the
# "size-sum:" line by helpers/size-sum.sh (production images mount only this
# script, hence the numfmt fallback).
REPO_SIZE_FILE=$(mktemp -t proxmox-reposize.XXXXXX)
trap 'rm -f "$REPO_SIZE_FILE"' EXIT
total=0
for d in "$WORKDIR/debian" "$WORKDIR/images" "$WORKDIR/iso"; do
  [ -d "$d" ] || continue
  sz=$(du -sb "$d" | cut -f1)
  total=$((total + sz))
done
echo "+$total" >> "$REPO_SIZE_FILE"
if [ -x "${_here}/helpers/size-sum.sh" ]; then
  "${_here}/helpers/size-sum.sh" "$REPO_SIZE_FILE" --rm
else
  echo "size-sum: $(numfmt --to=iec "$total")"
fi
