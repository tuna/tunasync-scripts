SHARE_DIR = "/opt/julia"

empty!(DEPOT_PATH)
push!(DEPOT_PATH, joinpath(homedir(), ".julia"), SHARE_DIR)
push!(LOAD_PATH, SHARE_DIR)
