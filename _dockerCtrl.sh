#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_BNAME=$(basename "$0")

# Validate configuration

if [ "$_BNAME" == "$(basename "${BASH_SOURCE[0]}")" ]; then
    echo "ERROR: $_BNAME must be sourced." 1>&2
    exit 1
fi

if [ -z "$_APP" -o -z "$_CONTAINER" -o -z "$_JSON_CONF" ]; then
    echo "ERROR: _APP, _CONTAINER, and _JSON_CONF must be defined." 1>&2
    exit 1
fi

_IMAGE=$(tr '[:upper:]' '[:lower:]' <<< "$_APP")

if [ -f "$_JSON_CONF" ]; then
    _jsonConf="$_JSON_CONF"
else
    _jsonConf="$_DIR/test/orbit/$_JSON_CONF"
    if [ ! -f "$_jsonConf" ]; then
	echo "ERROR: $_jsonConf not found!" 1>&2
	exit 1
    fi
fi

if [ "$1" == 'checkJSONConf' ]; then
    return
fi

if [ "$1" == 'define_endpoint_port' ]; then
    _path="$2"

    _port=$(grep -E -e "http://[^/:]+:[0-9]{4,5}/$_path" "$_jsonConf" | sed -E -e "s|.+http://.+:([0-9]{4,5})/$_path.*|\1|")

    if [ -z "$_port" ]; then
	echo "ERROR: no matching endpoint (\"$_path\") found in \"$_jsonConf\"." >&2
	exit 1
    fi

    return
fi

if [ "$1" == 'define_HZN_NODE_ID' ]; then
    _hostname=$(hostname)

    python3 - <<_EOF
import json
import sys

with open ("$_jsonConf", 'r') as _jIn:
    _jDict = json.load (_jIn)

if (_hilDict := _jDict.get ('HIL')) and \
   ("$_hostname" in _hilDict):
    sys.exit (0)
else:
    sys.exit (1)
_EOF

    if [ $? -eq 0 -o -n "$ANY_HOST" ]; then
	_HZN_NODE_ID="$_hostname"
    else
	echo "ERROR: \"$(hostname)\" is unregistered." 1>&2
	exit 1
    fi

    return
fi

_dFileBase=${DOCKERFILE:-Dockerfile._base}
if [ ! -f "$_dFileBase" ]; then
    echo "ERROR: $_dFileBase does not exist!" 1>&2
    exit 1
fi

_DOCKERFILE=Dockerfile.${_IMAGE}
rm -f "$_DOCKERFILE"
sed -E -e "s|_APP|$_APP|g" -e "s|_JSON|$_JSON_CONF|g" $_dFileBase > "$_DOCKERFILE"

if [ -n "$_MORE_DOCKER_CMDS" ]; then
    sed -Ei -e "s|^#_MORE_DOCKER_CMDS|$_MORE_DOCKER_CMDS|" "$_DOCKERFILE"
fi

####################
# Support routines #
####################

_getJSONValue()		# <key>
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

_usage()	# [<exit code>]
{
    local _ec=${1:-0}; shift
    local _fd=1

    if grep -Eq '^[12][0-9]{0,2}$' <<< "$_ec"; then
	_fd=2
    fi

    cat <<_EOF >&$_fd

Description:
    Builds "$_IMAGE" docker image and starts and controls associated "$_CONTAINER" container

Usage:

    $_BNAME [--help] [--force] <command> [<arg>]

    where <command> is
        build    provisionally builds docker image ("$_IMAGE")
        create   provisionally creates container ("$_CONTAINER")
        run      provisionally runs or starts container ("$_CONTAINER")
        stop     stops running container
        restart  restarts running container
        shell    executes an interactive shell in the running container
        log [clear]
                 clears or continuously displays application's console log
        status   displays image and container status
        pause    pauses running container
        resume   resumes/unpauses container
        signal <signal val>
                 sends signal to running container
        inspect [image]
                 inspects container ("$_CONTAINER") or image ("$_IMAGE")
        bcreate  builds docker image ("$_IMAGE") and creates container ("$_CONTAINER")
        brun     builds docker image ("$_IMAGE") and runs container ("$_CONTAINER")
        lcreate  creates container ("$_CONTAINER") and displays log
        lrun     runs container ("$_CONTAINER") and displays log
    and
        --force  automagically satisfies build, run, and shell command prerequisites

Note:

    To build an image on a host not specified in the JSON config file,
    run

        ANY_HOST=1 $_BNAME [--force] build
_EOF
    if [ -n "$_bareMetalInc" ]; then
        cat <<_EOF >&$_fd

    RUNNING ON BARE METAL
    ------- -- ---- -----
    To run "$_APP.py" directly on a host (cf., inside Docker containers), run

    $_BNAME [--help] (--bare | --metal) [build|prep]

    where
        build  satisfies installation dependencies but does not run "$_APP.py"
        prep
_EOF
    fi


    exit ${1:-0}
}

_imageInfo()
{
    docker image list --format '{{.Repository}}\t{{.ID}}\t{{.Size}}' $_IMAGE
}

_containerState()
{
    docker inspect --type container --format '{{.State.Status}}\t{{.State.Running}}\t{{.State.Paused}}\t{{.State.Restarting}}\t{{.State.OOMKilled}}\t{{.State.Dead}}\t{{.Config.Image}}' $_CONTAINER 2>/dev/null | \
    sed -E 's/\\t/\t/g'
}

_nthField()	# <n> <tab-delimited string>
{
    cut -f$1 <<< "$2"
}

_recurse()	# <command>
{
    DOCKERFILE=$_DOCKERFILE $_DIR/$_BNAME $_debugArg $_force $@
}

_recurseBase()	# <command>
{
    $_DIR/$_BNAME $_debugArg $_force $@
}

_promptForYesNo()	# <prompt string>
{
    if [ -n "$_force" ]; then
	return 0
    fi

    local _pStr="$@ [yN]? "
    local _yesNo

    while /bin/true; do
	read -p "$_pStr" _yesNo
	_yesNo=${_yesNo:-n}

	case $_yesNo in
	    y*|Y*)
		return 0
		;;
	    n*|N*)
		return 1
		;;
	    *)
		echo "...bad answer (\"$_yesNo\"); try again."
		;;
	esac
    done
}

_validateDockerGroup()
{
    if [ $UID -ne 0 ]; then
	local _g
	for _g in $(groups); do
	    if [ $_g == 'docker' ]; then
		_canRun=1
		break
	    fi
	done

	if [ -z "$_canRun" ]; then
            echo "ERROR: '$USER' is not in the 'docker' group; run 'sudo adduser $USER docker'." >&2
	    exit 1
	fi
    fi

    return 0
}

_checkForContainer()	# [additional checks...]
{
    local _cState=$(_containerState)
    if   [ -z "$_cState" ]; then
	echo "WARNING: \"$_CONTAINER\" container does not exist. Aborting." >&2
	return 1
    elif [ "$(_nthField $_sDead "$_cState")" == 'true' ]; then
	echo "WARNING: \"$_CONTAINER\" container was improperly or partially 'rm'd (viz, dead). Aborting." >&2
	return 1
    fi

    while [ -n "$1" ]; do
	local _arg="$1"; shift
	case "$_arg" in
	    running)
		if [ "$(_nthField $_sRunning "$_cState")" == 'false' ]; then
		    echo "\"$_CONTAINER\" is not running. Aborting." >&2
		    return 1
		fi
		;;
	    paused)
		if [ "$(_nthField $_sPaused "$_cState")" == 'false' ]; then
		    echo "\"$_CONTAINER\" is not paused. Aborting." >&2
		    return 1
		fi
		;;
	esac
    done

    return 0
}

_checkSignal()	# <signal>
{
    local _sig=$1; shift
    if [[ "$_sig" =~ [0-9]+ ]]; then
	local _fIndex=1
    else
	local _fIndex=2
	local _altSig=SIG$_sig
    fi

    while IFS= read -r _row; do
	local _rNam=$(cut -f2 <<< "$_row")

	if [ $_fIndex -eq 1 ]; then
	    local _rNum=$(cut -f1 <<< "$_row")
	    if [ $_sig -eq $_rNum ]; then
		echo "$_rNam"
		return
	    fi
	elif [ $_sig == $_rNam -o $_altSig == $_rNam ]; then
	    echo "$_rNam"
	    return
	fi
    done < <(kill -l | sed -E -e 's/^ +//' -e 's/ +$//' -e 's/ +/ /g' -e 's/\t */\n/g' -e 's/\) /\t/g' | grep -Ev '[-+]|^$')

    echo ''
}

_status()
{
    local _iInfo=$(_imageInfo)

    if [ -z "$_iInfo" ]; then
	echo '<No image>'
	return
    fi

    echo -e "IMAGE\tID\tSIZE\n$_iInfo"


    local _printLabels=1
    local _row

    while IFS= read -r _row; do
	if [ -z "$_labels" ]; then
	    local _labels="$_row"
	else
	    if grep -qE "  $_IMAGE$" <<< "$_row"; then
		if [ -n "$_printLabels" ]; then
		    echo ''
		    echo "$_labels"
		    _printLabels=
		fi
		echo "$_row"
	    fi
	fi
    done < <(docker ps --format 'table {{.Names}}\t{{.ID}}\t{{.Status}}\t{{.State}}\t{{.CreatedAt}}\t{{.Image}}' -a)
}

_rLog()	        # 'create' or 'run'
{
    _force='--force'
    if _recurseBase $1; then
        _recurseBase log
    fi

    exit $?
}

_rbLog()	# 'create' or 'run'
{
    _force='--force'
    if _recurseBase build; then
	_rLog $1
    fi

    exit $?
}

###########
# Globals #
###########

# Container state enumerated indices

_sStatus=1
_sRunning=2
_sPaused=3
_sRestarting=4
_sOOMKilled=5
_sDead=6
_cImage=7

_docker=docker

####################
# Main application #
####################

_validateDockerGroup

while [ -n "$1" ]; do
    _arg="$1"; shift
    case "$_arg" in
	--force|-f)
	    _force="$_arg"
	    ;;

	build)
	    if [ -n "$(_containerState)" ]; then
		if _promptForYesNo "Stop/remove container (\"$_CONTAINER\")"; then
		    $_docker container rm --force $_CONTAINER
		fi
	    fi

	    (cd $_DIR; $_docker build --file "$_DOCKERFILE" --tag $_IMAGE .)

	    exit $?
	    ;;

	bcreate)
	    _rbLog create
	    ;;

	brun)
	    _rbLog run
	    ;;

	lcreate)
	    _rLog create
	    ;;

	lrun)
	    _rLog run
	    ;;

	create)

	    # Provisionally create image

	    if [ -z "$(_imageInfo)" ]; then
		if ! _promptForYesNo "\"$_IMAGE\" image does not exist.  Build it"; then
		    echo "Create image aborted."
		    exit 1
		fi

		if ! _recurse build; then
		    exit $?
		fi
	    fi

	    if [ -n "$(_containerState)" ]; then
		echo "\"$_CONTAINER\" (already) exists."
		exit 0
	    fi

	    $_docker create \
		$_dockerCreateOpts \
		--name $_CONTAINER \
		$_IMAGE

	    exit $?
	    ;;

	run)
	    _cState="$(_containerState)"
	    if   [ "$(_nthField $_sRunning "$_cState")" == 'true' ]; then
		echo "\"$_CONTAINER\" is (already) running."
		exit 0

	    elif [ "$(_nthField $_sStatus "$_cState")" == 'exited' ]; then
		# Optional pre-run set up
		if [[ $(type -t _appPreRun) == function ]]; then
		    $_debug _appPreRun
		fi

		echo "Re-starting \"$_CONTAINER\""
		$_docker container start $_CONTAINER
		exit $?

	    elif [ "$(_nthField $_sRestarting "$_cState")" == 'true' ]; then
		echo "\"$_CONTAINER\" is restarting; waiting 5 seconds..."
		sleep 5
		_recurse run
		exit $?

	    elif [ "$(_nthField $_sDead "$_cState")" == 'true' ]; then
		echo "WARNING: \"$_CONTAINER\" was improperly or partially 'rm'd (viz, dead). Aborting." >&2
		exit 1
	    fi

	    # Provisionally create container

	    if [ -z "$_cState" ]; then
		if ! _promptForYesNo "\"$_CONTAINER\" container does not exist.  Build it"; then
		    echo "Run container aborted."
		    exit 1
		fi

		if ! _recurse create; then
		    exit $?
		fi
	    fi

	    # Start the container

	    $_docker container start \
		$_CONTAINER

	    exit $?
	    ;;

	stop)
	    if _checkForContainer running; then
		_recurse signal SIGINT
	    fi
	    exit $?
	    ;;

	restart)
	    if _checkForContainer running; then
		_recurse signal SIGHUP
	    fi
	    exit $?
	    ;;

	shell)
	    if _checkForContainer running; then
		$_docker container exec -it $_CONTAINER /bin/bash
	    fi
	    exit $?
	    ;;

	log)
	    _conLog=$(docker inspect --format='{{.LogPath}}' $_CONTAINER)

	    if [ "$1" == 'clear' ]; then
		if [ -n "$_conLog" ]; then
		    _cState="$(_containerState)"
		    if   [ "$(_nthField $_sRunning    "$_cState")" == 'true' -o \
			   "$(_nthField $_sRestarting "$_cState")" == 'true' \
			 ]; then
			if _promptForYesNo "Stop container (\"$_CONTAINER\")"; then
			    _recurse signal SIGINT
			else
			    exit 0
			fi
		    fi

		    sudo truncate --size=0 "$_conLog"
		fi

		exit $?
	    fi

	    if [ -n "$_conLog" ]; then
		$_docker container logs -f $_CONTAINER
	    fi

	    exit $?
	    ;;

	status)
	    _status
	    exit $?
	    ;;

	pause)
	    if _checkForContainer running; then
		$_docker container pause $_CONTAINER
	    fi
	    exit $?
	    ;;

	resume|unpause)
	    if _checkForContainer paused; then
		$_docker container unpause $_CONTAINER
	    fi
	    exit $?
	    ;;

	signal)
	    if _checkForContainer running; then
		_sig=$1; shift
		_mSig=$(_checkSignal $_sig)	# validate signal argument
		if [ -n "$_mSig" ]; then
		    $_docker container kill --signal $_mSig $_CONTAINER
		else
		    echo "ERROR: unknown signal ($_sig)" >&2
		    /bin/false
		fi
	    fi
	    exit $?
	    ;;

	inspect)
	    case $1 in
		i*)
		    if [ -n "$(_imageInfo)" ]; then
			$_docker image inspect "$_IMAGE"
		    else
			echo "ERROR: no image ($_IMAGE)" >&2
			false
		    fi
		    ;;
		*)
		    if _checkForContainer; then
			$_docker container inspect $_CONTAINER
		    fi
		    ;;
	    esac

	    exit $?
	    ;;

	--help|-h)
	    _usage
	    ;;

	--debug|-d)
	    _debug=echo
	    _debugArg="$_arg"
	    _docker='echo docker'
	    ;;

	*)
	    echo "ERROR: unknown command (\"$_arg\")." >&2
	    _usage 1
	    ;;
    esac
done

_usage
