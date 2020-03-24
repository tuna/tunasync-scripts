FROM debian:buster
MAINTAINER Wang Ruikang <dramforever@live.com>

RUN apt-get update && \
    apt-get install -y python3-dev python3-pip && \
    pip3 install pyquery requests minio && \
    # Install Nix. To simplify management we only copy binaries and create
    # symlinks, and do no further configuration
    curl https://mirrors.tuna.tsinghua.edu.cn/nix/nix-2.3.2/nix-2.3.2-x86_64-linux.tar.xz -o /tmp/nix.tar.xz && \
    mkdir /tmp/nix.unpack && \
    tar xpf /tmp/nix.tar.xz -C /tmp/nix.unpack && \
    mkdir /nix && \
    cp -dpr /tmp/nix.unpack/*/store /nix/store && \
    ln -s /nix/store/*-nix-*/bin/* /usr/local/bin && \
    rm -rf /tmp/nix.tar.xz /tmp/nix.unpack

ENV HOME=/tmp
CMD /bin/bash
