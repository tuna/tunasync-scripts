#!/bin/bash
sz=`bc <$1`
echo "size-sum:" $(numfmt --to=iec $sz)
