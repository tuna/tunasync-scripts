FROM ruby:3.3-alpine

RUN gem install --no-document rubygems-mirror --version 1.3.0 && \
    rm -rf /usr/local/bundle/cache && \
    apk add --no-cache bash curl

# The timeout command provided by BusyBox is now compatible with coreutils.
ENV BUSYBOX=0
ENV HOME=/tmp
