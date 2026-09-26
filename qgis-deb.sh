#!/bin/bash
set -e
set -o pipefail

_here=$(dirname "$(realpath "$0")")
apt_sync="${_here}/apt-sync.py"

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://qgis.org"}"

if [ -z "${TUNASYNC_WORKING_DIR:-}" ]; then
    echo "ERROR: TUNASYNC_WORKING_DIR is not set; refusing to sync into /debian etc." >&2
    exit 2
fi
WORKDIR="${TUNASYNC_WORKING_DIR}"

REPO_SIZE_FILE=$(mktemp -t qgis-deb-reposize.XXXXXX)
export REPO_SIZE_FILE

# Both Debian and Ubuntu codenames are listed on purpose: the qgis.org S3
# backend serves the union of both families under each tree (verified
# 2026-09-25: /debian/dists/jammy and /ubuntu/dists/bookworm both exist),
# and apt-sync.py --delete removes any on-disk .deb not referenced by the
# codenames synced in this run. Splitting the list per tree would delete
# still-published content; codenames absent upstream are filtered out by
# the probe in sync_repo() before syncing. Stale/EOL codenames that
# upstream still serves (buster, kinetic, lunar, mantic, oracular) are
# intentionally not mirrored.
DEB_CODENAMES="bullseye,bookworm,trixie,sid,unstable,jammy,noble,resolute,plucky,questing,focal,xenial,bionic"
DEB_ARCHES="amd64,i386"

UBUNTUGIS_CODENAMES="jammy,noble,bionic,focal,xenial"
UBUNTUGIS_ARCHES="amd64"

# Sync one apt tree. apt-sync.py always exits 0 (it only logs failures), so
# failures are detected from its "Failed APT repos" log line instead of the
# exit code. Codenames whose Release file is gone upstream (the S3 backend
# answers 403/404 for missing keys) are skipped; if such a codename was
# mirrored before, its local dists tree is removed first so that --delete
# can garbage-collect its packages and the mirror never serves a
# half-retired distribution.
sync_repo() {
    local repo=$1 codenames=$2 component=$3 arches=$4 dest=$5
    local keep=() c code
    for c in ${codenames//,/ }; do
        code=$(curl -sL -o /dev/null -w '%{http_code}' --retry 2 --retry-all-errors \
            --connect-timeout 10 --max-time 30 \
            -I "${BASE_URL}/${repo}/dists/${c}/Release") || code=000
        if [ "$code" = "200" ]; then
            keep+=("$c")
        elif [ "$code" = "404" ] || [ "$code" = "403" ]; then
            if [ -d "${dest}/dists/${c}" ]; then
                echo "WARNING: ${repo}/dists/${c} is gone upstream (HTTP ${code}); removing the retired local copy" >&2
                rm -rf "${dest}/dists/${c}"
            else
                echo "NOTE: ${repo}/dists/${c} not provided upstream (HTTP ${code}); skipping" >&2
            fi
        else
            echo "WARNING: probing ${repo}/dists/${c}/Release failed (HTTP ${code}); keeping it in the sync list" >&2
            keep+=("$c")
        fi
    done
    if [ ${#keep[@]} -eq 0 ]; then
        echo "ERROR: no codenames of ${repo} are available upstream; refusing to sync an empty tree" >&2
        return 1
    fi
    local joined log rc=0
    joined=$(IFS=,; echo "${keep[*]}")
    log=$(mktemp -t qgis-deb-aptsync.XXXXXX)
    "$apt_sync" --delete "${BASE_URL}/${repo}" "$joined" "$component" "$arches" "$dest" 2>&1 | tee "$log" || rc=$?
    if [ "$rc" -ne 0 ] || grep -q "Failed APT repos" "$log"; then
        rm -f "$log"
        echo "ERROR: apt-sync reported failures for ${repo}" >&2
        return 1
    fi
    rm -f "$log"
    echo "${repo} finished"
}

sync_repo debian       "$DEB_CODENAMES"       main "$DEB_ARCHES"       "${WORKDIR}/debian"
sync_repo debian-ltr   "$DEB_CODENAMES"       main "$DEB_ARCHES"       "${WORKDIR}/debian-ltr"
sync_repo ubuntugis    "$UBUNTUGIS_CODENAMES" main "$UBUNTUGIS_ARCHES" "${WORKDIR}/ubuntugis"
sync_repo ubuntugis-ltr "$UBUNTUGIS_CODENAMES" main "$UBUNTUGIS_ARCHES" "${WORKDIR}/ubuntugis-ltr"

# ubuntu is byte-identical to debian upstream (Release sha256 matched for
# every codename, verified 2026-09-25), and ubuntu-ltr likewise mirrors
# debian-ltr, so serve both as symlinks. ln -T treats the destination as
# the link itself; refuse to replace a real directory left behind by an
# older mirror layout instead of nesting into it.
make_link() {
    local name=$1 target=$2
    if [ -d "${WORKDIR}/${name}" ] && [ ! -L "${WORKDIR}/${name}" ]; then
        echo "ERROR: ${WORKDIR}/${name} is a real directory; remove it before creating the symlink" >&2
        exit 1
    fi
    ln -sfnT "$target" "${WORKDIR}/${name}"
    echo "${name} -> ${target} symlink created"
}
make_link ubuntu debian
make_link ubuntu-ltr debian-ltr

# size-sum.sh only aggregates REPO_SIZE_FILE for the tunasync size report;
# a failure here is non-fatal and must not fail the whole sync. --rm removes
# the temp file on success; on failure the container's /tmp is ephemeral.
"${_here}/helpers/size-sum.sh" "$REPO_SIZE_FILE" --rm || \
    echo "WARNING: size-sum.sh failed; repo size not updated" >&2
