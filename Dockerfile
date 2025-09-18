FROM debian:trixie
LABEL maintainer="Miao Wang <miao.wang@tuna.tsinghua.edu.cn>"

RUN apt-get update && \
        apt-get install --no-install-recommends -y \
        wget curl rsync lftp git jq \
        python3-dev python3-pip python3-pyquery python3-socks python3-requests python3-yaml awscli \
        dnf-plugins-core createrepo-c yum debmirror \
        libnss-unknown xz-utils patch unzip \
        aria2 ack openssh-client
        # composer php-curl php-zip

RUN if [ "$(uname -m)" != "x86_64" -a "$(uname -m)" != "i386" ]; then \
      apt-get install --no-install-recommends -y libxml2-dev libxslt1-dev zlib1g-dev libssl-dev libffi-dev ;\
    fi

# RUN pip3 install --upgrade pip
RUN python3 -m pip install \
    # for flutter, needs unpublished version of apitools, see: https://github.com/GoogleCloudPlatform/gsutil/issues/1819
    gsutil https://github.com/google/apitools/archive/refs/tags/v0.5.35.zip \
    # for shadowmire
    requests tqdm click \
    --break-system-packages

RUN echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && apt-get install -y locales -qq && locale-gen
ENV LANG=en_US.UTF-8 LANGUAGE=en_US.UTF-8 LC_ALL=en_US.UTF-8 HOME=/tmp
RUN mkdir -p /home/tunasync-scripts
CMD ["/bin/bash"]


# ====================
# customizations

# patch awscli
RUN cd /usr/lib/python3/dist-packages && echo "/Td6WFoAAATm1rRGAgAhARYAAAB0L+Wj4AHCAPNdADIaSQnC/BF9UN4KT0fVpgATRDuLqRGmPehqSjhNcR3ZqGVBKbVF3r5L2cNs3c+prOthcy3s42Nc79kbE7aRKiQ2r/ivJlWIiio5V2qwWq9aggjTJauhCHLTxXwQiVFDoburbJ4tJYXGnFzOXgYuHjXBWfLKmvshuOMAPYbiPOAgtnQX/8F2sFep7K+0c7/J4HZ6K6ynW121t9pYxX0q6zDZLJBD93rt9Lr/cYC2Eozop6t/ahQsgL1oS1vBXTsA/wQkU0HXOGJ2sJ4J1ULbop82QES9m5CXagcx9EDe7nfJD1UXGgQjif8HCl8y6KFw3rdiPQAAudB1OELBZ/0AAY8CwwMAAAHezTCxxGf7AgAAAAAEWVo=" | base64 -d | xzcat | patch -p1

# download composer-mirror
# RUN cd /usr/local && git clone --depth 1 https://github.com/tuna/composer-mirror.git && cd composer-mirror && composer i
# COPY composer-mirror.config.php /usr/local/composer-mirror/config.php

# download and patch aosp-repo
ADD --chmod=0755 https://storage.googleapis.com/git-repo-downloads/repo /usr/local/bin/aosp-repo
RUN sed -i 's:^#!/usr/bin/env python$:#!/usr/bin/env python3:' /usr/local/bin/aosp-repo

# install ed for debmirror
RUN apt-get install --no-install-recommends -y ed
