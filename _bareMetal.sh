#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_BNAME=$(basename "$0")

# Validate configuration

if [ "$_BNAME" == "$(basename "${BASH_SOURCE[0]}")" ]; then
    echo "ERROR: $_BNAME must be sourced." 1>&2
    exit 1
fi

# Check CLI options

for _a in $@; do
    case $_a in
	--bare|--metal)
	    _bareMetal="$_a"
	    ;;

	-d|--debug)
	    _debug=echo
	    ;;

	supportOnly)
	    _supportOnly=1	# for manual debugging
	    ;;
    esac
done

if [ -z "$_bareMetal" ]; then
    _bareMetalInc='included'	# _dockerCtrl.sh signal
    return
fi

####################
# Support routines #
####################

_usage()	# [<exit code>]
{
    local _ec=${1:-0}; shift
    local _fd=1

    if grep -Eq '^[12][0-9]{0,2}$' <<< "$_ec"; then
	_fd=2
    fi

    cat <<_EOF >&$_fd

Description:
    Runs "$_APP.py" directly on a host.

Usage:

    $_BNAME [--help] [build|prep]

    where
        build  satisfies installation dependencies but does not run "$_APP.py"
        prep

_EOF

    exit ${1:-0}
}

_nthField()	# <n> <tab-delimited string>
{
    cut -f$1 <<< "$2"
}

_hasPyModule()	# <module>
{
    grep -Eq "^(.+ +)?$1( +.+)?$" <<< "$_pymods"
}

_aptInstall()	# <mod> <vers>
{
    local _mod=$1
    local _mVers=$2

    # Search for package

    local _pLine=$(grep -E "^$_mod[[:space:]]" $_tmpAptPy3)

    if [ -z "$_pLine" ]; then
	echo "ERROR: unable to install \"$_mod$_mVers\"" >&2
	return 1	# package not found
    fi

    # Optionally compare available version

    if [ -n "$_mVers" ]; then
	if ! _hasPyModule semver; then
	    if ! $_debug sudo apt install -y python3-semver; then
		return $?	# semver not found
	    fi
	fi

	_pkgVer=$(_nthField 3 "$_pLine")
	
	local _vParts
	IFS=',' read -r -a _vParts <<< "$_mVers"

	for _mVer in ${_vParts[@]}; do
	    if ! _semverMatch "$_pkgVer" "$_mVer"; then
		echo "ERROR: $_mod $_pkgVer doesn't satisfy $_mVer" >&2
		return 1	# version mismatch
	    fi
	done
    fi

    echo "apt install python3-$_mod:"
    $_debug sudo apt install -y python3-$_mod
}

_semverMatch()		# <ver> <match ver>
{
    python3 -c "import semver; exit (0 if semver.match (\"$1\", \"$2\") else 1)"
}

_checkPip()
{
    if ! which pip3 >& /dev/null; then
	echo "pip must be installed. Please enter your password:"
	_aptInstall pip
    fi
}

_prepPyMods()
{
    # Determine if python's modules are externally managed

    local _pyExtMng=$(python3 -c 'import os, sysconfig; print (os.path.join (sysconfig.get_path("stdlib", sysconfig.get_default_scheme ()), "EXTERNALLY-MANAGED"))')
    if [ -f "$_pyExtMng" ]; then
	_pyAptMng=1

	# Create python3 apt list for _aptInstall ()

	_tmpAptPy3="/tmp/.$$_apt_list_py3"
	apt list 'python3*' 2>/dev/null | \
	    grep -E '^python3' | \
	    sed -E -e 's|/| |g' -e 's| |\t|g' -e 's|^python3-||' \
		> $_tmpAptPy3
    fi

    # Cache the list of installed Python modules

    _pymods=$(python3 -c 'help("modules")' 2>/dev/null)
}

_postPyMods()
{
    if [ -n "$_pyAptMng" -a -f "$_tmpAptPy3" ]; then
	rm "$_tmpAptPy3"
    fi
}

_aptOrCheckPip()	# <pip req>
{
    # Check requirements file

    local _pipReq
    for _pipReq in "$1" "$_SRC_DIR/$1"; do
	if [ -f "$_pipReq" ]; then
	    break
	else
	    unset _pipReq
	fi
    done

    if [ -z "$_pipReq" ]; then
	return 1
    fi

    # Compare the required modules against those installed or installable

    if [ -n "$_debug" ]; then
	echo "$_pipReq"
    fi

    local _modSpec
    while IFS= read -r _modSpec; do
	if [ -z "$_modSpec" ]; then
	    continue
	fi

	_mod=$(_nthField 1 "$_modSpec")

	if [[ $_mod =~ -r|--requirements ]]; then
	    # Recurse
	    if _aptOrCheckPip $(_nthField 2 "$_modSpec"); then
		return 0	# install via pip3
	    fi

	elif ! _hasPyModule $_mod; then
	    if [ -n "$_pyAptMng" ]; then
		if ! _aptInstall $_modSpec; then
		    _eStatus=$?
		fi
	    else
		return 0	# install via pip3
	    fi
	fi
    done < <(sed -E -e 's/^ *(-r|--requirement) +([^# ]+).*/\1\t\2/' -e 's| +||' -e 's|[#;].*||g' -e 's|~=|!=|' -e 's|([_0-9A-Za-z]+)([<>=!].*)|\1\t\2|' < "$_pipReq")

    return 1
}

if [ -n "$_supportOnly" ]; then
    return
fi

############################
# Check required variables #
############################

if [ -z "$_APP" -o -z "$_JSON_CONF" ]; then
    echo "ERROR: _APP and _JSON_CONF must be defined." 1>&2
    exit 1
fi

if [ -f "$_JSON_CONF" ]; then
    _jsonConf="$_JSON_CONF"
else
    _jsonConf="$_DIR/test/orbit/$_JSON_CONF"
    if [ ! -f "$_jsonConf" ]; then
	echo "ERROR: $_jsonConf not found!" 1>&2
	exit 1
    fi
fi

####################
# Main application #
####################

while [ -n "$1" ]; do
    _arg="$1"; shift
    case "$_arg" in
	build|prep)
	    _build=1
	    ;;
	--debug|-d)
	    _debug=echo
	    ;;
	--help|-h)
	    _usage
	    ;;
    esac
done

# Check for required Python modules

_SRC_DIR="$_DIR/src/python"

_PY_REQ="$_SRC_DIR/requirements-$_APP.txt"
if [ -f "$_PY_REQ" ]; then
    _prepPyMods

    if _aptOrCheckPip "$_PY_REQ"; then
	_checkPip
	cd "$_SRC_DIR"
	$_debug pip3 install -r "$_PY_REQ"
	cd -
    fi

    _postPyMods
fi

# Define environment variables

_ENV_DECL='PYTHONPATH=.'
for _tok in $_dockerCreateOpts; do
    if [ "$_lastTok" == '--env' ]; then
	_ENV_DECL="$_ENV_DECL $_tok"
	unset _lastTok
    elif [ "$_tok" == '--env' ]; then
	_lastTok="$_tok"
    fi
done

# Optional prep

if [[ $(type -t _bareMetalPrep) == function ]]; then
    $_debug _bareMetalPrep
fi

if [ -n "$_build" ]; then
    exit $?
fi

# Optional pre-run

if [[ $(type -t _appPreRun) == function ]]; then
    $_debug _appPreRun
fi

# Run code

env --chdir=$_SRC_DIR $_ENV_DECL $_debug python3 -u $_APP.py $_jsonConf

exit $?
