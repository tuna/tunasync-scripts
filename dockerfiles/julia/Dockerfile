FROM python:3.6
LABEL description="A community maintained docker script to set up julia mirror easily."
LABEL maintainer="Johnny Chen <johnnychen94@hotmail.com>"

ENV JULIA_DEPOT_PATH="/tmp/julia"
ENV JULIA_STATIC_DIR="/julia/static"
ENV JULIA_CLONES_DIR="/julia/clones"

RUN pip install --upgrade pip && \
    pip install jill==0.6.8 && \
    pip cache purge

RUN jill install 1.4 --confirm

WORKDIR /julia
RUN julia -e 'using Pkg; pkg"add https://github.com/johnnychen94/StorageServer.jl#v0.1.0-beta.1"'

CMD /bin/bash
