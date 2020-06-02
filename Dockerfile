FROM debian:buster
MAINTAINER Justin Wong <yuzhi.wang@tuna.tsinghua.edu.cn>

RUN apt-get update && \
        apt-get install -y wget curl rsync lftp git jq python3-dev python3-pip yum-utils createrepo aria2 ack composer php-curl php-zip
        
RUN STATIC_DEPS=true pip3 install pyquery
RUN pip3 install requests[socks] pyyaml gsutil awscli bandersnatch==3.6.0

RUN cd /usr/local && git clone --depth 1 https://github.com/tuna/composer-mirror.git && cd composer-mirror && composer i
COPY composer-mirror.config.php /usr/local/composer-mirror/config.php

RUN mkdir -p /home/tunasync-scripts
ADD https://storage.googleapis.com/git-repo-downloads/repo /usr/local/bin/aosp-repo
RUN chmod 0755 /usr/local/bin/aosp-repo

RUN echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && apt-get install -y locales -qq && locale-gen
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

ENV HOME=/tmp
CMD /bin/bash
