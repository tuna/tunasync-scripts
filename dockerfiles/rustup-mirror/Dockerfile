FROM rust:trixie AS builder

ARG CRATE_VERSION
RUN test -n "$CRATE_VERSION" && \
    cargo install --locked --root /build --version "=$CRATE_VERSION" rustup-mirror

FROM debian:trixie-slim
LABEL maintainer="Jiajie Chen <jiegec@noc.ac.cn>"

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/bin/rustup-mirror /usr/local/cargo/bin/rustup-mirror

CMD ["/bin/bash"]
