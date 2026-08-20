FROM debian:trixie-slim AS source

RUN apt-get update && \
	apt-get install -y --no-install-recommends ca-certificates git && \
	rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://ftp-master.debian.org/git/archvsync.git/ /ftpsync/ && \
	revision="$(git -C /ftpsync rev-parse --short HEAD)" && \
	sed -i "s/^VERSION=.*/VERSION=\"g${revision}\"/" /ftpsync/bin/include-git && \
	rm -rf /ftpsync/.git

FROM debian:trixie-slim
LABEL maintainer="Miao Wang <miao.wang@tuna.tsinghua.edu.cn>"

RUN apt-get update && \
	apt-get install -y --no-install-recommends rsync stunnel4 socat ca-certificates opensysusers && \
	rm -rf /var/lib/apt/lists/*

COPY --from=source /ftpsync/ /ftpsync/

WORKDIR /ftpsync/
ENV PATH=/ftpsync/bin:${PATH}
CMD ["/bin/bash"]
