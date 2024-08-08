ARG PY_VERSION=3.11

FROM python:${PY_VERSION}-alpine

WORKDIR /home/scripts

RUN pip3 install requests tqdm click
COPY shadowmire.py .
CMD /bin/bash
