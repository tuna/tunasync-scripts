FROM rust:trixie
LABEL maintainer="Jiajie Chen <jiegec@noc.ac.cn>"

# used to skip caching on new version release
ADD "https://crates.io/api/v1/crates/rustup-mirror" "crates_version.json"
RUN cargo install rustup-mirror
CMD ["/bin/bash"]
