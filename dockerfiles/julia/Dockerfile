# For the details and usage of this docker script, please refer to:
# * https://github.com/tuna/tunasync-scripts/pull/71
# * https://github.com/tuna/issues/issues/837

# jill.py requires at least Python 3.6
FROM python:3.6
LABEL description="A community maintained docker script to set up julia mirror easily."
LABEL maintainer="Johnny Chen <johnnychen94@hotmail.com>"

ENV JULIA_DEPOT_PATH="/tmp/julia"
ENV JULIA_STATIC_DIR="/julia/static"
ENV JULIA_CLONES_DIR="/julia/clones"

# jill.py provides two functionalities:
#   1) mirror julia binary releases
#   2) install julia in one line
# FYI: the jill API is quite stable so the version doesn't matter much (it could be okay to set >=0.6.9)
RUN pip install --upgrade pip && \
    pip install jill==0.6.9 && \
    pip cache purge

# StorageServer.jl is used to set up a *static* storage server for julia packages, it requires at least Julia 1.4
# The details of the storage protocol can be found in https://github.com/JuliaLang/Pkg.jl/issues/1377
RUN jill install 1.4 --confirm

# StorageServer.jl is an experimental toolkit and it won't be registered in General
# The API is likely to be changed in the future, so we fix the version here for stability consideration
RUN julia -e 'using Pkg; pkg"add https://github.com/johnnychen94/StorageServer.jl#v0.1.0-beta.1"'

RUN chown -R 2000 /tmp/julia/

WORKDIR /julia
CMD /bin/bash
