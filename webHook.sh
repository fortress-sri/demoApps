#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

####################
# Support routines #
####################

_getJSONValue()         # <key>
{
    python3 - <<_EOF 2>/dev/null
#!/usr/bin/env python3

import json

with open ('$_jsonConf', 'r') as _jIn:
    _jDict = json.load (_jIn)

if _jVal := _jDict.get ("$1"):
    print (_jVal)
_EOF
}

###############
# App pre-run #
###############
_appPreRun()
{
    # Provisionally start ssh reverse tunnel

    local _whSSH=$(_getJSONValue 'WebHook-tunnel')
    if [ -n "$_whSSH" ]; then
        if [ -n "$_debug" ]; then
            _whSSH=$(sed -e 's|ssh|ssh -vvv|' <<< "$_whSSH")
        fi

        local _whPort=$(sed -E -e 's|.+ -R [^ ]+:([0-9]{4,5}) .+|\1|' <<< "$_whSSH")
        if [ -n "$_whPort" ]; then

            # Provisionally copy the private key

            local _privKey=$(sed -E -e 's|.+ -i +([^ ]+).+|\1|' <<< "$_whSSH")
            _privKey=${_privKey/#\~/$HOME}

            if [ ! -f $_privKey -a -f "$_DIR/test/webhook/webhook_tun" ]; then
                cp -v "$_DIR/test/webhook/webhook_tun" $_privKey
                chmod 400 $_privKey
            fi

            # Check for pre-existing ssh tunnel

            local _psSSH=$(ps uxwwwww | grep "$_whSSH" | grep -v grep)
            if [ -z "$_psSSH" ]; then
                echo "Starting ssh reverse tunnel"
                $_whSSH
            fi

            # Check if app is already running (TCP port is listening)

            local _whPortNetTCP=$($_DIR/util/proc_net_tcp.py | grep -E -e ".+ any:$_whPort +.+ +0A +")
            if [ -n "$_whPortNetTCP" ]; then
                echo "WARNING: $_APP is already running." >&2
                exit 0
            fi
        fi
    fi
}

###########
# Globals #
###########

_APP=webHook
_CONTAINER=web_hook_app
_JSON_CONF="${JSON_CONF}"               # test/orbit/*.json

source "$_DIR/_dockerCtrl.sh" define_endpoint_port api/webHook
_dockerCreateOpts="--env HOST=0.0.0.0 --env PORT=$_port --publish $_port:$_port"

_bareMetal=1    # comment out to enable containerization
source "$_DIR/_bareMetal.sh"

DOCKERFILE="$_DIR/Dockerfile._qApp"

source "$_DIR/_dockerCtrl.sh"
