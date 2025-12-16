#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_defBNS='/app/bns'

while [ -n "$1" ]; do
    case "$1" in
	--bns|-B)
	    shift
	    _bns="$1"
	    ;;
        -d|--debug)
            _debug=echo
            ;;
        -h|--help|'-?')
            cat <<_EOF
 Usage: $(basename "$0") [--bns|-B <bns>]

    --bns	bns source directory (default: "$_defBNS")
_EOF
            exit 0
            ;;
        *)
            echo "Unknown option: \"$1\"." 1>&2
            exit 1
            ;;
    esac
    shift
done

_bns=${_bns:-$_defBNS}

if [ ! -d "$_bns" ]; then
    echo "ERROR: \"$_bns\" not found." 1>&2
    exit 1
fi

cd "$_bns"

if [ -n "$_debug" ]; then
    echo "$_DIR  $_bns"
    ls -FCal
    git branch -a
    #cat .git/config
fi

patch -p1 < "$_DIR/bns.patch"
