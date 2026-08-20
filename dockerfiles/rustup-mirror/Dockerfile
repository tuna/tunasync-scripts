FROM rust:trixie AS builder

# used to skip caching on new version release
ADD "https://crates.io/api/v1/crates/rustup-mirror" "crates_version.json"
RUN cargo install --root /build rustup-mirror

FROM debian:trixie-slim
LABEL maintainer="Jiajie Chen <jiegec@noc.ac.cn>"

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/bin/rustup-mirror /usr/local/cargo/bin/rustup-mirror

CMD ["/bin/bash"]
