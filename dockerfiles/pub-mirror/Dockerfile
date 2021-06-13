FROM debian:stable AS dart-build

ARG DART_VERSION="2.12.4"

WORKDIR /tmp/

RUN \
  apt-get -q update && apt-get install --no-install-recommends -y -q \
    gnupg2 curl git ca-certificates unzip openssh-client && \
  case "$(uname -m)" in armv7l | armv7) ARCH="arm";; aarch64) ARCH="arm64";; *) ARCH="x64";; esac && \
  curl -O https://storage.googleapis.com/dart-archive/channels/stable/release/$DART_VERSION/sdk/dartsdk-linux-$ARCH-release.zip && \
  unzip dartsdk-linux-$ARCH-release.zip -d /usr/lib/ && \
  rm dartsdk-linux-$ARCH-release.zip && \
  mv /usr/lib/dart-sdk /usr/lib/dart && \
  chmod -R "og+rX" /usr/lib/dart

ENV DART_SDK /usr/lib/dart
ENV PATH $DART_SDK/bin:/root/.pub-cache/bin:$PATH
WORKDIR /root

RUN set -eux; \
  ( case "$(uname -m)" in \
    armv7l | armv7) ARCH="arm-linux-gnueabihf" ; \
      echo "/lib/ld-linux-armhf.so.3" ; \
      echo "/lib/arm-linux-gnueabihf/ld-linux-armhf.so.3" ;; \
    aarch64) ARCH="aarch64-linux-gnu" ; \
      echo "/lib/ld-linux-aarch64.so.1" ; \
      echo "/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1" ;; \
    *) ARCH="x86_64-linux-gnu" ; \
      echo "/lib64/ld-linux-x86-64.so.2" ;; \
  esac; \
  echo "/etc/nsswitch.conf"; \
  echo "/etc/ssl/certs"; \
  echo "/usr/share/ca-certificates"; \
  echo "/bin/bash"; echo "/bin/sh"; \
  for i in libc.so.6 libdl.so.2 libm.so.6 libnss_dns.so.2 libpthread.so.0 \
    libresolv.so.2 librt.so.1 libtinfo.so.6; do \
    echo "/lib/$ARCH/$i"; \
  done \
  ) | while read p; do \
    dir="$(dirname "$p")"; \
    mkdir -p "/runtime$dir"; \
    cp --archive --link --dereference --no-target-directory "$p" "/runtime$p"; \
  done

FROM dart-build
MAINTAINER Hui Yiqun <i@huiyiqun.me>

ENV PUB_CACHE /pub-cache

RUN pub global activate -s git https://github.com/tuna/pub-mirror.git

CMD /bin/bash
