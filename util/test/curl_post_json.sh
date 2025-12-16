#!/bin/sh

_url=$1
_json=$2

curl --header "Content-Type: application/json" \
     --request POST \
     --data @$_json \
     $_url
