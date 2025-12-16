#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

###########
# Globals #
###########

_APP=geo_table_server
_CONTAINER=dynamic-table
_JSON_CONF="${JSON_CONF}"		# test/orbit/*.json

source "$_DIR/_dockerCtrl.sh" define_endpoint_port api/record
_dockerCreateOpts="--env HOST=0.0.0.0 --env PORT=$_port --publish $_port:$_port"

source "$_DIR/_bareMetal.sh"

DOCKERFILE="$_DIR/Dockerfile._qApp"

source "$_DIR/_dockerCtrl.sh"
