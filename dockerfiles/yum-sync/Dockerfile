FROM centos:8
MAINTAINER Hongren Zheng <hongren.zheng@tuna.tsinghua.edu.cn>

RUN dnf makecache && \
        dnf install -y 'dnf-command(reposync)' createrepo_c wget curl

RUN mkdir -p /home/tunasync-scripts

ENV HOME=/tmp
CMD /bin/bash
