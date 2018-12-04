FROM python:3-stretch
MAINTAINER Justin Wong <yuzhi.wang@tuna.tsinghua.edu.cn>

RUN echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ stretch main contrib non-free" > /etc/apt/sources.list && \
        echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ stretch-backports main contrib non-free" >> /etc/apt/sources.list && \
        echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ stretch-updates main contrib non-free" >> /etc/apt/sources.list && \
        echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian-security/ stretch/updates main contrib non-free" >> /etc/apt/sources.list

RUN apt-get update && \
        apt-get install -y wget curl rsync lftp git jq python-dev python-pip yum-utils createrepo aria2

RUN pip3 install bandersnatch==3.1.2
        
RUN STATIC_DEPS=true pip3 install pyquery
RUN pip3 install requests pyyaml

RUN mkdir -p /home/tunasync-scripts
ADD https://storage.googleapis.com/git-repo-downloads/repo /usr/local/bin/aosp-repo
RUN chmod a+x /usr/local/bin/aosp-repo

RUN echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && apt-get install -y locales -qq && locale-gen
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

ENV HOME=/tmp
CMD /bin/bash
