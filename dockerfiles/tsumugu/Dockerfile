FROM rust:trixie AS builder

ARG CRATE_VERSION
RUN test -n "$CRATE_VERSION" && \
    cargo install --locked --bin tsumugu --root /build --version "=$CRATE_VERSION" tsumugu

FROM debian:trixie-slim
LABEL maintainer="Shengqi Chen <i@harrychen.xyz>"

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/bin/tsumugu /usr/local/bin

CMD ["/bin/bash"]
