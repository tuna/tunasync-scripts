FROM rust:trixie AS builder

# Pinned commit for reproducible builds; pass --build-arg GIT_REF=<sha/tag/branch>
# to build another revision (--rev accepts all three).
ARG GIT_REF=02134d51b2a98c98ed0dbb45901c94b4c6a1d671
RUN test -n "$GIT_REF" && \
    cargo install --locked --root /build --git https://github.com/sjtug/mirror-clone.git --rev "$GIT_REF" mirror-clone

FROM debian:trixie-slim
LABEL maintainer="Nanjing University LUG <lug@nju.edu.cn>"

# rsync: the mirror-clone rsync source shells out to it (src/rsync.rs).
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates rsync && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/bin/mirror-clone /usr/local/bin/mirror-clone

CMD ["/bin/bash"]
