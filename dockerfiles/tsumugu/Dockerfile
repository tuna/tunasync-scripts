FROM rust:trixie
LABEL maintainer="Shengqi Chen <i@harrychen.xyz>"

# used to skip caching on new version release
ADD "https://crates.io/api/v1/crates/tsumugu" "crates_version.json"
RUN cargo install tsumugu
CMD ["/bin/bash"]
