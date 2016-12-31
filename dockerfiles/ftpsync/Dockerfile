FROM debian:jessie
MAINTAINER Justin Wong <yuzhi.wang@tuna.tsinghua.edu.cn>

RUN echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ jessie main contrib non-free" > /etc/apt/sources.list && \
	echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ jessie-backports main contrib non-free" >> /etc/apt/sources.list && \
	echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ jessie-updates main contrib non-free" >> /etc/apt/sources.list && \
	echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian-security/ jessie/updates main contrib non-free" >> /etc/apt/sources.list

RUN apt-get update && \
	apt-get install -y git rsync && \
	apt-get install -y -t jessie-backports stunnel4 socat && \
	apt-get clean all

RUN git clone https://ftp-master.debian.org/git/archvsync.git/ /ftpsync/
WORKDIR /ftpsync/
ENV PATH /ftpsync/bin:${PATH}
CMD /bin/bash

