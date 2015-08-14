#!/bin/bash

# Invoke from the gut source folder, e.g.:
# DEST=/some/path scripts/cross_compile.sh

set -e
: ${DEST?"Need to set DEST"}

rm -f gut
CWD=$(pwd)
for OS in darwin linux freebsd
do
    for ARCH in 386 amd64
    do
        cd $GOROOT/src
        GOOS=$OS GOARCH=$ARCH ./make.bash
        cd $CWD
        GOOS=$OS GOARCH=$ARCH go build
        gzip gut
        mv gut.gz $DEST/gut-$OS-$ARCH.gz
    done
done
