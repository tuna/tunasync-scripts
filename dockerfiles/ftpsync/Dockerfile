FROM debian:stretch
MAINTAINER Justin Wong <yuzhi.wang@tuna.tsinghua.edu.cn>

RUN apt-get update && \
	apt-get install -y git rsync awscli stunnel4 socat && \
	apt-get clean all

RUN git clone https://ftp-master.debian.org/git/archvsync.git/ /ftpsync/
WORKDIR /ftpsync/
ENV PATH /ftpsync/bin:${PATH}
CMD /bin/bash

