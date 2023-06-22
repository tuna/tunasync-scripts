#!/bin/bash
# requires: coreutils
[[ -f "$1" ]] || exit 0
sz=$(cat $1)
sz=$((0$sz))
echo "size-sum:" $(numfmt --to=iec $sz)
[[ "$2" == "--rm" ]] && rm "$1"
