#!/bin/bash
set -e -u -o pipefail
shopt -s lastpipe

_here=$(dirname "$(realpath $0)")
BASE_PATH="${TUNASYNC_WORKING_DIR}"
TUNASYNC_UPSTREAM_URL=${TUNASYNC_UPSTREAM_URL:-"https://nodejs.org/dist"}
TUNASYNC_LFTP_OPTIONS=${TUNASYNC_LFTP_OPTIONS:-""}

cd "$BASE_PATH"

skip_links="--exclude-glob latest/** --exclude-glob latest-*/** --exclude-glob node-latest* --exclude-glob latest --exclude-glob latest-* --exclude-glob index.json --exclude-glob .index.json.tmp"

curl -fsSL --remote-time "$TUNASYNC_UPSTREAM_URL/index.json" --output "$BASE_PATH/.index.json.tmp"

declare -A links

jq -r '
  def semver: .version | ltrimstr("v") | split(".") | map(tonumber);
  def line: semver as $v | if $v[0] == 0 then "v0.\($v[1]).x" else "v\($v[0]).x" end;
  def newest: max_by(semver).version;

  newest as $latest
  | [ {key: "latest", value: $latest},
      {key: "node-latest.tar.gz", value: "latest/node-\($latest).tar.gz"} ]
  + (group_by(line) | map({key: "latest-\(.[0] | line)", value: newest})
     | map(select((.key | startswith("latest-v0.") | not)
                  or .key == "latest-v0.10.x" or .key == "latest-v0.12.x")))
  + (map(select(.lts)) | group_by(.lts)
     | map({key: "latest-\(.[0].lts | ascii_downcase)", value: newest}))
  | .[] | "\(.key) \(.value)"' "$BASE_PATH/.index.json.tmp" |
  while IFS=" " read -r key value; do
    links["$key"]="$value"
  done

TUNASYNC_LFTP_OPTIONS="${TUNASYNC_LFTP_OPTIONS} ${skip_links}" "$_here/lftp.sh" || true

link_if_changed() {
    local src=$1
    local dest=$2
    if [ -L "$dest" ]; then
        local current_src
        current_src=$(readlink "$dest")
        if [ "$current_src" = "$src" ]; then
            echo "Link unchanged: $dest -> $src" >&2
            return
        fi
    fi
    ln -s -v -T -f "$src" "$dest"
}

for key in "${!links[@]}"; do
    link_if_changed "${links[$key]}" "$BASE_PATH/$key"
done

find "$BASE_PATH" -type l -name "*latest*" -printf '%P\n' |
  while IFS= read -r link; do
    if [ -z "${links[$link]+isset}" ]; then
        echo "Removing stale link: $BASE_PATH/$link" >&2
        rm -f "$BASE_PATH/$link"
    fi
  done

mv "$BASE_PATH/.index.json.tmp" "$BASE_PATH/index.json"
