#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

###################
# Bare metal prep #
###################
_bareMetalPrep()
{
    local _bnsDir="$_SRC_DIR/bns"
    if [ ! -d "$_bnsDir" ]; then
	cd "$_SRC_DIR"
	$_debug git clone https://github.com/0xShun/Basic_Network_Scanner.git
	$_debug mv Basic_Network_Scanner bns
	cd -

	$_debug "$_DIR/tmp_patch_bns/patch_bns.sh" --bns "$_SRC_DIR/bns"
    fi
}

###########
# Globals #
###########

_APP=thirdPartyApp
_CONTAINER=non_critical_app
_JSON_CONF="${JSON_CONF:-thirdParty.json}"		# test/orbit/*.json

source "$_DIR/_dockerCtrl.sh" define_HZN_NODE_ID
_dockerCreateOpts="--env HZN_NODE_ID=$_HZN_NODE_ID"

source "$_DIR/_bareMetal.sh"

source "$_DIR/_dockerCtrl.sh" checkJSONConf

DOCKERFILE="$_DIR/Dockerfile._3rd"

source "$_DIR/_dockerCtrl.sh"
