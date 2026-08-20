FROM rust:trixie AS builder

RUN cargo install \
    --git https://github.com/open-rust-initiative/freighter \
    --root /build

FROM debian:trixie-slim
LABEL maintainer="Aron Xu <happyaron.xu@gmail.com>"

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/bin/freighter-registry /usr/local/cargo/bin/freighter-registry

CMD ["/bin/bash"]
