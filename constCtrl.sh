#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


###########
# Globals #
###########

_APP=constApp
_CONTAINER=constellation-sim
_JSON_CONF="${JSON_CONF}"		# test/orbit/*.json

_dockerCreateOpts="$_dockerCreateOpts --env SAT_DEBUG=enable"

source "$_DIR/_bareMetal.sh"

DOCKERFILE="$_DIR/Dockerfile._const"

source "$_DIR/_dockerCtrl.sh"
