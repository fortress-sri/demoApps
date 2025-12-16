#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


###########
# Globals #
###########

_APP=satApp
_CONTAINER=edge-node
_JSON_CONF="${JSON_CONF}"		# test/orbit/*.json

source "$_DIR/_dockerCtrl.sh" define_HZN_NODE_ID
_dockerCreateOpts="$_dockerCreateOpts --env HZN_NODE_ID=$_HZN_NODE_ID"

source "$_DIR/_bareMetal.sh"

source "$_DIR/_dockerCtrl.sh"
