FROM python:3-buster
MAINTAINER Wang Ruikang <dramforever@live.com>

RUN curl https://mirrors.tuna.tsinghua.edu.cn/nix/nix-2.3.2/nix-2.3.2-x86_64-linux.tar.xz -o /tmp/nix.tar.xz

RUN pip3 install pyquery requests

# Install Nix. To simplify management we only copy binaries and create
# symlinks, and do no further configuration

RUN mkdir /tmp/nix.unpack && \
    tar xpf /tmp/nix.tar.xz -C /tmp/nix.unpack && \
    mkdir /nix && \
    cp -dpr /tmp/nix.unpack/*/store /nix/store && \
    ln -s /nix/store/*-nix-*/bin/* /usr/local/bin && \
    rm -rf /tmp/nix.tar.xz /tmp/nix.unpack

ENV HOME=/tmp
CMD /bin/bash
