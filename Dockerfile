FROM debian:jessie
MAINTAINER Justin Wong <yuzhi.wang@tuna.tsinghua.edu.cn>

RUN echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ jessie main contrib non-free" > /etc/apt/sources.list && \
        echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ jessie-backports main contrib non-free" >> /etc/apt/sources.list && \
        echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ jessie-updates main contrib non-free" >> /etc/apt/sources.list && \
        echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian-security/ jessie/updates main contrib non-free" >> /etc/apt/sources.list

RUN apt-get update && \
        apt-get install -y wget curl rsync lftp git jq python-dev python-pip yum-utils createrepo python3-dev python3-pip aria2

RUN pip install --upgrade pip setuptools && \
        pip install bandersnatch==1.11
        
RUN pip3 install requests pyyaml

RUN mkdir -p /home/tunasync-scripts
ADD https://storage.googleapis.com/git-repo-downloads/repo /usr/local/bin/aosp-repo
RUN chmod a+x /usr/local/bin/aosp-repo
RUN apt-get install -y python3-lxml && pip3 install pyquery

RUN echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && apt-get install -y locales -qq && locale-gen
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

ENV HOME=/tmp
CMD /bin/bash
