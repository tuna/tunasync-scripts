# RETIRED: use shadowmire instead

ARG PY_VERSION=3.12

FROM python:${PY_VERSION}-alpine

RUN apk add --update --no-cache --virtual .build-deps \
        g++ \
        bash \
        python3-dev \
        libxml2 \
        libxml2-dev && \
    apk add libxslt-dev
RUN pip3 install bandersnatch
CMD /bin/bash
