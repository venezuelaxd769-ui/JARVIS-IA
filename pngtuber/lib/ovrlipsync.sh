#!/bin/sh
# this script runs ovrlipsync through wine, since it's not officially available on linux

wine "${1%.*}.exe" $2
