#!/bin/bash

if [ -z "$HZN_NODE_ID" ]; then
    echo "ERROR: \"HZN_NODE_ID\" is undefined." >&2
    exit 1
fi

echo exec $*
exec $*
