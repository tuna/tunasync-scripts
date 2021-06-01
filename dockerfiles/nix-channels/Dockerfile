FROM debian:buster
MAINTAINER Wang Ruikang <dramforever@live.com>

RUN apt-get update && \
    apt-get install -y python3-dev python3-pip curl 
RUN if [ "$(uname -m)" != "x86_64" -a "$(uname -m)" != "i386" ]; then \
      apt-get install -y libxml2-dev libxslt1-dev zlib1g-dev ;\
    fi
RUN pip3 install pyquery requests minio==5.0.10 
    # Install Nix. To simplify management we only copy binaries and create
    # symlinks, and do no further configuration
RUN mkdir -p /tmp/nix.unpack && \
    curl -L https://mirrors.tuna.tsinghua.edu.cn/nix/nix-2.3.2/nix-2.3.2-$(arch)-linux.tar.xz | tar -xpJ -C /tmp/nix.unpack && \
    mkdir /nix && \
    cp -dpr /tmp/nix.unpack/*/store /nix/store && \
    ln -s /nix/store/*-nix-*/bin/* /usr/local/bin && \
    rm -rf /tmp/nix.unpack

ENV HOME=/tmp
CMD /bin/bash
