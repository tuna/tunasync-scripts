FROM ruby:2.7-alpine
RUN gem install rubygems-mirror
RUN apk add bash
# the command timeout provided by old verison of busybox was incompatible with that from coreutils and is compatible now. 
ENV BUSYBOX=0
ENV HOME=/tmp
