FROM python:3.6
MAINTAINER Justin Wong <yuzhi.wang@tuna.tsinghua.edu.cn>

RUN echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ jessie main contrib non-free" > /etc/apt/sources.list && \
        echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ jessie-backports main contrib non-free" >> /etc/apt/sources.list && \
        echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ jessie-updates main contrib non-free" >> /etc/apt/sources.list && \
        echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian-security/ jessie/updates main contrib non-free" >> /etc/apt/sources.list

RUN apt-get update && \
        apt-get install -y git aria2

RUN pip3 install requests pyyaml

RUN echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && apt-get install -y locales -qq && locale-gen
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

ENV HOME=/tmp
CMD /bin/bash
