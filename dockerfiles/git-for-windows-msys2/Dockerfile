FROM golang:1.17.0-bullseye AS builder
WORKDIR /usr/src/
RUN apt-get update && \
        apt-get install -y git
RUN git clone https://github.com/Azure/azure-storage-azcopy
RUN cd azure-storage-azcopy && git checkout v10.12.1 && go build -o azcopy

FROM alpine:3.12
LABEL maintainer="hongren.zheng@tuna.tsinghua.edu.cn"
COPY --from=builder /usr/src/azure-storage-azcopy/azcopy /usr/local/bin/

RUN mkdir -p /home/tunasync-scripts
CMD /bin/bash
