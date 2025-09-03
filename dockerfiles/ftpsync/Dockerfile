FROM debian:trixie
LABEL maintainer="Miao Wang <miao.wang@tuna.tsinghua.edu.cn>"

RUN apt-get update && \
	apt-get install -y --no-install-recommends git rsync stunnel4 socat ca-certificates opensysusers && \
	apt-get clean all

RUN git clone https://ftp-master.debian.org/git/archvsync.git/ /ftpsync/
WORKDIR /ftpsync/
ENV PATH /ftpsync/bin:${PATH}
CMD ["/bin/bash"]

