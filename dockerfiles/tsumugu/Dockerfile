FROM rust:trixie AS builder
LABEL maintainer="Shengqi Chen <i@harrychen.xyz>"

# used to skip caching on new version release
ADD "https://crates.io/api/v1/crates/tsumugu" "crates_version.json"
RUN mkdir -p /build
RUN cargo install --bin tsumugu --root /build tsumugu

FROM debian:trixie
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates
COPY --from=builder /build/bin/tsumugu /usr/local/bin
CMD ["/bin/bash"]
