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
    julia -e 'using Pkg; pkg"add https://github.com/johnnychen94/StorageMirrorServer.jl#v0.1.1-rc3"' && \
    chmod a+rx -R $JULIA_DEPOT_PATH

COPY dockerfiles/julia/startup.jl /usr/local/julia/etc/julia/startup.jl

WORKDIR /julia
CMD /bin/bash
