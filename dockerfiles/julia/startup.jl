# makes /opt/julia a shared depot path so that users can directly find and load
# pre-installed packages
#
# For non-root users, /opt/julia is read-only, trying to add packages would be impossible.
# A workaround for this is to start julia with a project folder that is writable, e.g.,
# `julia --project=$HOME/.julia/env/1.5"`

SHARE_DIR = "/opt/julia"

empty!(DEPOT_PATH)
push!(DEPOT_PATH, joinpath(homedir(), ".julia"), SHARE_DIR)
push!(LOAD_PATH, SHARE_DIR)
