FROM debian:trixie-slim AS python-builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-pip && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install \
    --break-system-packages \
    --no-compile \
    --no-deps \
    --no-cache-dir \
    --target /opt/python-packages \
    minio==5.0.10

FROM debian:trixie-slim AS nix-builder

ARG NIX_VERSION=2.3.2

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl xz-utils && \
    rm -rf /var/lib/apt/lists/*

RUN case "$(dpkg --print-architecture)" in \
      amd64) nix_arch=x86_64 ;; \
      arm64) nix_arch=aarch64 ;; \
      *) echo "Unsupported architecture: $(dpkg --print-architecture)" >&2; exit 1 ;; \
    esac && \
    mkdir -p /tmp/nix.unpack /nix && \
    curl --fail --location --show-error \
      "https://mirrors.tuna.tsinghua.edu.cn/nix/nix-${NIX_VERSION}/nix-${NIX_VERSION}-${nix_arch}-linux.tar.xz" \
      | tar -xpJ -C /tmp/nix.unpack && \
    cp -dpr /tmp/nix.unpack/*/store /nix/store

FROM debian:trixie-slim
LABEL maintainer="Wang Ruikang <dramforever@live.com>"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates python3 python3-dateutil python3-pyquery python3-pytz python3-requests && \
    rm -rf /var/lib/apt/lists/*

COPY --from=python-builder /opt/python-packages /opt/python-packages
COPY --from=nix-builder /nix /nix

RUN ln -s /nix/store/*-nix-*/bin/* /usr/local/bin

ENV HOME=/tmp PYTHONPATH=/opt/python-packages
CMD ["/bin/bash"]
