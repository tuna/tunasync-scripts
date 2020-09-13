#!/bin/bash

TUNASYNC_WORKING_DIR="${TUNASYNC_WORKING_DIR:-nix}"

TUNASYNC_UPSTREAM_URL="${TUNASYNC_UPSTREAM_URL:-s3://nix-releases/nix/}"
MIRROR_BASE_URL="${MIRROR_BASE_URL:-https://mirrors.tuna.tsinghua.edu.cn/nix}"
ORIG_BASE_URL="https://nixos.org/releases/nix"

EXCLUDES=(--exclude "*/*/*" \
    --exclude "nix-[01].*" \
    --exclude "nix-2.[01][./]*" \
    --exclude "*-broken*")

INSTALL_TEMP="$(mktemp -d .tmp.XXXXXX)"
trap 'rm -rf "$INSTALL_TEMP"' EXIT

[[ ! -d "${TUNASYNC_WORKING_DIR}" ]] && mkdir -p "${TUNASYNC_WORKING_DIR}"
cd "${TUNASYNC_WORKING_DIR}"
aws --no-sign-request s3 sync ${TUNASYNC_AWS_OPTIONS} \
    "${EXCLUDES[@]}" \
    --exclude "*/install" \
    --exclude "*/install.asc" \
    --exclude "*/install.sha256" \
    "${TUNASYNC_UPSTREAM_URL}" .

# Create install script

aws --no-sign-request s3 sync ${TUNASYNC_AWS_OPTIONS} \
    --exclude "*" \
    --include "*/install" \
    "${EXCLUDES[@]}" \
    "${TUNASYNC_UPSTREAM_URL}" "${INSTALL_TEMP}"

for version in $(ls "$INSTALL_TEMP"); do
    [[ ! -d "${version}" ]] && continue # Shouldn't happen

    sed -e "s|${ORIG_BASE_URL}|${MIRROR_BASE_URL}|" \
        < "${INSTALL_TEMP}/${version}/install" \
        > "${INSTALL_TEMP}/${version}/.install"
    mv "${INSTALL_TEMP}/${version}/.install" "${version}/install"

    sha256sum "${version}/install" | cut -d' ' -f1 | tr -d '\n' \
        > "${INSTALL_TEMP}/${version}/.install.sha256"
    mv "${INSTALL_TEMP}/${version}/.install.sha256" "${version}/install.sha256"
done

ln -sfn "$(ls -d nix-* | sort -rV | head -1)" latest
