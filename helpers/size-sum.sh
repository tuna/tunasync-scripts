#!/bin/bash
# requires: coreutils
sz=$(cat $1)
sz=$(($sz))
echo "size-sum:" $(numfmt --to=iec $sz)
