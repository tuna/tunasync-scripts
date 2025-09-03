# For the details and usage of this docker script, please refer to:
# * https://github.com/tuna/tunasync-scripts/pull/71
# * https://github.com/tuna/issues/issues/837

# StorageServer.jl is used to set up a *static* storage server for julia packages, it requires at least Julia 1.4
# The details of the storage protocol can be found in https://github.com/JuliaLang/Pkg.jl/issues/1377
FROM julia:1.5
LABEL description="A community maintained docker script to set up julia mirror easily."
LABEL maintainer="Johnny Chen <johnnychen94@hotmail.com>"

ENV JULIA_DEPOT_PATH="/opt/julia"

RUN adduser --uid 2000 tunasync && \
    julia -e 'using Pkg; pkg"add StorageMirrorServer@0.2.0"' && \
    chmod a+rx -R $JULIA_DEPOT_PATH

# Julia doesn't not yet have a nice solution for centralized package system with preinstalled
# packages. Here we provide a system-wide startup.jl that modifies the DEPOT_PATH and LOAD_PATH
# variables for each user.
# For more information about this, please refer to https://github.com/JuliaLang/Pkg.jl/issues/1952
COPY dockerfiles/julia/startup.jl /usr/local/julia/etc/julia/startup.jl

WORKDIR /julia
CMD /bin/bash
