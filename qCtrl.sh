#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

###########
# Globals #
###########

_APP=QController
_CONTAINER=demo-coordinator
_JSON_CONF="${JSON_CONF}"		# test/orbit/*.json

source "$_DIR/_bareMetal.sh"

source "$_DIR/_dockerCtrl.sh" checkJSONConf

while IFS= read -r _port; do
    _dockerCreateOpts="--publish $_port:$_port $_dockerCreateOpts"
done < <(grep -E -e '.*"Q-.+": ".+://' "$_jsonConf" | sed -E -e 's|.*:([0-9]{4,5}).*|\1|')

if [ -z "$_dockerCreateOpts" ]; then
    echo "ERROR: no matching endpoint(s) found in \"$_jsonConf\"." >&2
    exit 1
fi

DOCKERFILE="$_DIR/Dockerfile._qApp"

source "$_DIR/_dockerCtrl.sh"
