#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

###########
# Globals #
###########

_APP=orbitApp
_CONTAINER=constellation
_JSON_CONF=satTest.json		# test/orbit/*.json

source "$_DIR/_dockerCtrl.sh"
