#!/bin/bash
sz=$(cat $1)
sz=$(echo $sz | bc)
echo "size-sum:" $(numfmt --to=iec $sz)
