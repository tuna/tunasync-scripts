ARG PY_VERSION=3.13

FROM python:${PY_VERSION}-alpine

WORKDIR /home/scripts

RUN apk add --update --no-cache --virtual .build-deps bash
RUN pip3 install requests tqdm click
COPY shadowmire.py .
CMD ["/bin/bash"]
