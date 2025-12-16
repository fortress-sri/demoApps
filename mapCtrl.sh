#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

###################
# Bare metal prep #
###################
_bareMetalPrep()
{
    rsync -a --progress "$_SRC_DIR/img/" "$_SRC_DIR/template/" "$_SRC_DIR"
}

###########
# Globals #
###########

_APP=geo_map_server
_CONTAINER=flat-earth-display
_JSON_CONF="${JSON_CONF}"		# test/orbit/*.json

source "$_DIR/_dockerCtrl.sh" define_endpoint_port api/marker
_dockerCreateOpts="--env HOST=0.0.0.0 --env PORT=$_port --publish $_port:$_port"

source "$_DIR/_bareMetal.sh"

DOCKERFILE="$_DIR/Dockerfile._qApp"

_MORE_DOCKER_CMDS='COPY src/python/img/*.jpg src/python/template .'

source "$_DIR/_dockerCtrl.sh"
