FROM rust:bookworm
MAINTAINER Aron Xu <happyaron.xu@gmail.com>

RUN set -e; \
    git clone --depth=1 https://github.com/open-rust-initiative/freighter; \
    cd freighter; \
    cargo build --release; \
    mkdir -p /root/freighter; \
    cp /freighter/target/release/freighter /usr/local/bin/

#COPY dockerfiles/freighter/config.toml /root/freighter/
    
WORKDIR /root/freighter
CMD /bin/bash
