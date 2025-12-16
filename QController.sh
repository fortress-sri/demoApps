#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

####################
# Support routines #
####################

_ithField()	# <index>
{
    cut -f$1 <<< "${2:-$_qEPLine}"
}

_checkConf()	# <JSON config>
{
    while IFS= read -r _ifn; do
	if [ -f "$_ifn" ]; then
	    echo "$_ifn"
	    return
	fi
    done <<_EOF
$1
$_DIR/test/orbit/$1
$_DIR/test/orbit/$1.json
_EOF

    echo ''	# no config file found
}

_postAction()	# <action> <arg> ...
{
    local _action=$1; shift
    local _expr

    while [ -n "$1" ]; do
    	case "$1" in
    	    disable)
		if [ -n "$_expr" ]; then
		    _expr="$_expr, \"enable\": false"
		else
		    _expr="\"enable\": false"
		fi
		;;

	    3rd|third*)
		local _class=thirdParty
		if [ -n "$_expr" ]; then
		    _expr="$_expr, \"class\": \"$_class\""
		else
		    _expr="\"class\": \"$_class\""
		fi
		;;

	    sat*|node)
		local _class=sat
		if [ -n "$_expr" ]; then
		    _expr="$_expr, \"class\": \"$_class\""
		else
		    _expr="\"class\": \"$_class\""
		fi
		;;

	    hil)
		local _class=hil
		if [ -n "$_expr" ]; then
		    _expr="$_expr, \"class\": \"$_class\""
		else
		    _expr="\"class\": \"$_class\""
		fi
		;;

	    [a-zA-Z]*)	# lookup HIL
		local _po=$(_getJSONElement lookup "$1")
		if [ -n "$_po" ]; then
		    local _plane=$(_ithField 1 "$_po")
		    local _ordinal=$(_ithField 2 "$_po")
		    _poStr="\"plane\": \"$_plane\", \"ordinal\": \"$_ordinal\""
		    if [ -n "$_expr" ]; then
			_expr="$_expr, $_poStr"
		    else
			_expr="$_poStr"
		    fi
		fi
		;;

	    [1-9]*)
		if [ -n "$_plane" ]; then
		    local _ordinal="$1"
		    _expr="$_expr, \"ordinal\": \"$_ordinal\""
		else
		    local _plane="$1"
		    if [ -n "$_expr" ]; then
			_expr="$_expr, \"plane\": \"$_plane\""
		    else
			_expr="\"plane\": \"$_plane\""
		    fi
		fi
		;;
	esac

	shift
    done

    local _action_json=$$-action_tmp.json
    cat <<__EOF__ > $_action_json
{
  $_expr
}
__EOF__
    _curl_post $_action $_action_json
    rm -f $_action_json
}

_getJSONElement()	# <action> [<arg> ...]
{
    #cat <<_EOF 2>/dev/null
    python3 - <<_EOF 2>/dev/null
#!/usr/bin/env python3

import json
import os
import sys
from   urllib.parse import urlparse

_file   = "$_satConf"
_action = "$1".lower ()

if not os.path.isfile (_file):
    print (f'ERROR: "{_file}" does not exist.')
    sys.exit (1)

try:
    with open (_file, 'r') as _jIn:
        _jDict = json.load (_jIn)
        if isinstance (_jDict, dict):

            # Q-endpoint

            if   _action == 'endpoint':
                if _qRegEP := _jDict.get ('Q-endpoint'):
                    _pResult = urlparse (_qRegEP)
                    if _pResult.scheme == 'http' and _pResult.netloc:
                        _nlParts = _pResult.netloc.split (':')
                        _msg = f'{_pResult.scheme}://{_pResult.netloc}/nodes\t{_nlParts[0]}'
                        if len (_nlParts) == 2:
                            _msg += f'\t{_nlParts[1]}'
                        print (_msg)

            # HIL stanza

            elif _action in ('hil', 'lookup'):
                if _hil := _jDict.get ('HIL'):
                    if   _action == 'hil':
                        print (json.dumps (_hil, indent = 4, sort_keys = True))

                    elif _action == 'lookup':
                        _key = "$2"
                        if _po := _hil.get (_key):
                            if isinstance (_po, str):
                                _parts = _po.split (',')
                            else:
                                _parts = list ([str (_po)])
                            if len (_parts) == 1:
                                _parts.insert (0, '1')
                            print ('\t'.join (_parts))                        
except Exception as _e:
    print (f'ERROR: {_e}')
    sys.exit (1)
_EOF
}

_nc()      # [abend_str]
{
    local _abend=$1; shift

    nc -z $_qEPHost $_qEPPort > /dev/null 2>&1

    local _retVal=$?

    if [ -n "$_abend" -a $_retVal -ne 0 ]; then
        echo "ERROR: $_abend @ $_qEPHost:$_qEPPort isn't available or reachable." 1>&2
    fi

    return $_retVal
}

_fmtJSON()
{
    local _tmpJSON="/tmp/$$_fmtJSON.json"

    tee "$_tmpJSON" | python3 -m json.tool 2>/dev/null

    if [ $? -ne 0 ]; then
        cat "$_tmpJSON"
    fi

    rm -f "$_tmpJSON"
}

_curl_cmd()
{
    # Check external server

    if _nc QController; then
        local _path=$1; shift

	curl -s $* "$_qEPURL/$_path" | _fmtJSON
	echo ""
    else
        exit 1
    fi
}

_curl_get()
{
    local _path=$1; shift

    _curl_cmd $_path $*
}

_curl_post()
{
    local _path=$1; shift
    local _json=$1; shift

    _curl_cmd $_path \
              --header "Content-Type: application/json" \
              --request POST \
              --data @$_json
}

_usage()	# [<exit code>]
{
    local _ec=${1:-0}; shift
    local _fd=1

    if grep -Eq '^[12][0-9]{0,2}$' <<< "$_ec"; then
	_fd=2
    fi

    cat <<_EOF >&$_fd

Description:
    Communicates with Q Controller

Usage:

    $(basename "$0") [--help] [<JSON conf>] <command>

    where <command> is
        stop [<node spec>] [<app class>]
                   stops specified application class, where <app class>
                   is 'node', 'sat*', '3rd', 'third*', 'hil', or
                   (implicitly) any
        debug [<node spec>] [disable]
                   enables or disables satellite intervals debug mode
        exfilt [<node spec>] [disable]
                   enables or disables satellite intervals exfiltration
        thirdParty [<node spec>]
                   enables third party nmap application
        info       shows registered satellite intervals
        hil        shows configured Hardware-In-the-Loop (HIL) hosts

    and

        <node spec> is
            <plane range> [<ordinal range>]
          or
            <HIL hostname>

    The ancillary development <command>

        _start     sends start notification to satellites; this is
                   needed when there are fewer running satellites than
                   are specified in the JSON configuration

Note:

    If the environment variable, JSON_CONF, is defined, viz.,

       export JSON_CONF=<JSON conf>

    then the <JSON conf> CLI argument is not required.

_EOF

    exit ${1:-0}
}

########
# Main #
########

_satConf=$(_checkConf "$JSON_CONF")	# Check environment variable

# Process arguments

while [ -n "$1" ]; do
    case "$1" in
	stop|debug|exfilt|thirdParty|info|hil|_start)
	    _cmd=$1
	    if [ -n "$_satConf" ]; then
		shift
		break
	    fi
	    ;;

	-h|--help)
	    _usage
	    ;;

	*)
	    if [ -z "$_satConf" ]; then
		_satConf=$(_checkConf "$1")
		if [ -z "$_satConf" ]; then
		    echo "ERROR: unrecognized command (\"$1\")" >&2
		    _usage 1
		fi
	    elif [ -n "$_cmd" ]; then
		break
	    else
		echo "ERROR: unrecognized command (\"$1\")" >&2
		_usage 1
	    fi
	    ;;
    esac

    shift
done

# Validate arguments

if [ -z "$_cmd" ]; then
    echo 'WARNING: missing <command>' >&2
    _usage 1
fi

if [ -z "$_satConf" ]; then
    echo 'ERROR: missing or bad satellite JSON file' >&2
    _usage 1
fi

_qEPLine=$(_getJSONElement endpoint)
_qEPURL=$(_ithField 1)
_qEPHost=$(_ithField 2)
_qEPPort=$(_ithField 3)

if [[ ! "$_qEPPort" =~ [0-9]{4,6} ]]; then
    echo "ERROR: bad or missing endpoint port ($_qEPPort)" >&2
    exit 2
fi

# Check for tunneled port

if netstat -ant | grep -Eq " +127.0.0.1.$_qEPPort.+ +LISTEN *"; then
    _qEPURL="$(sed -E -e "s|$_qEPHost|127.0.0.1|" <<< "$_qEPURL")"
    _qEPHost='127.0.0.1'
fi

# Run command

case "$_cmd" in
    stop|debug|exfilt|thirdParty)
	_postAction $_cmd $*
	;;

    info)
	_curl_get info
	;;

    hil)
	_getJSONElement hil
	;;

    _start)
	_curl_get _start
	;;
esac
