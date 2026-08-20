FROM rust:trixie AS builder

# used to skip caching on new version release
ADD "https://crates.io/api/v1/crates/tsumugu" "crates_version.json"
RUN cargo install --bin tsumugu --root /build tsumugu

FROM debian:trixie-slim
LABEL maintainer="Shengqi Chen <i@harrychen.xyz>"

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/bin/tsumugu /usr/local/bin

CMD ["/bin/bash"]
