#!/bin/bash
set -e
set -o pipefail

_here=$(dirname "$(realpath "$0")")
apt_sync="${_here}/apt-sync.py"

BASE_URL="${TUNASYNC_UPSTREAM_URL:-"https://qgis.org"}"
WORKDIR="${TUNASYNC_WORKING_DIR}"
export REPO_SIZE_FILE="/tmp/reposize.$RANDOM"

DEB_CODENAMES="bullseye,bookworm,trixie,jammy,noble,resolute,plucky,questing,focal,xenial,bionic"
DEB_ARCHES="amd64,i386"

UBUNTUGIS_CODENAMES="jammy,noble,bionic,focal,xenial"
UBUNTUGIS_ARCHES="amd64"

"$apt_sync" --delete "${BASE_URL}/debian"      "$DEB_CODENAMES"     main "$DEB_ARCHES"      "${WORKDIR}/debian"
echo "debian finished"

"$apt_sync" --delete "${BASE_URL}/debian-ltr"  "$DEB_CODENAMES"     main "$DEB_ARCHES"      "${WORKDIR}/debian-ltr"
echo "debian-ltr finished"

"$apt_sync" --delete "${BASE_URL}/ubuntu"      "$DEB_CODENAMES"     main "$DEB_ARCHES"      "${WORKDIR}/ubuntu"
echo "ubuntu finished"

"$apt_sync" --delete "${BASE_URL}/ubuntugis"   "$UBUNTUGIS_CODENAMES" main "$UBUNTUGIS_ARCHES" "${WORKDIR}/ubuntugis"
echo "ubuntugis finished"

"$apt_sync" --delete "${BASE_URL}/ubuntugis-ltr" "$UBUNTUGIS_CODENAMES" main "$UBUNTUGIS_ARCHES" "${WORKDIR}/ubuntugis-ltr"
echo "ubuntugis-ltr finished"

# ubuntu-ltr is a symlink to debian-ltr (identical content)
ln -sfn debian-ltr "${WORKDIR}/ubuntu-ltr"
echo "ubuntu-ltr symlink created"

"${_here}/helpers/size-sum.sh" "$REPO_SIZE_FILE" --rm || true
