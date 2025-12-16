#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "$JSON_CONF" ]; then
    _JSON_DIR="$_DIR/../../test/orbit"
    while IFS= read -r _ifn; do
	if [ -f "$_ifn" ]; then

	    # Search for flat earth display endpoint

	    _mEPHP=$(grep -E -e '.+http://.+:[0-9]{4,5}/api/marker.+' "$_ifn" | \
		     sed -E -e 's|.+http://(.+:[0-9]{4,5})/.+|\1|')

	    # Extract host and port

	    if [ -n "$_mEPHP" ]; then
		_mEPPort="$(cut -d: -f2 <<< "$_mEPHP")"
		# Check for tunneled port
		if [ -n "$_mEPPort" ]; then
		    if netstat -ant | grep -Eq " +127.0.0.1.$_mEPPort.+ +LISTEN *"; then
			_mEPHost='127.0.0.1'
		    else
			_mEPHost="$(cut -d: -f1 <<< "$_mEPHP")"
		    fi
		fi
		break
	    fi
	fi
    done <<_EOF
$JSON_CONF
$_JSON_DIR/$JSON_CONF
$_JSON_DIR/$JSON_CONF.json
_EOF
fi

_GEOM_URL="http://${_mEPHost:-127.0.0.1}:${_mEPPort:-5000}/api"

_curl_post() {		# <endpoint> <json>
    "$_DIR/curl_post_json.sh" "$_GEOM_URL/$1" $2 | python3 -m json.tool
    echo ""
}

_update_marker() {	# <label> <lat> <lon> [<color>]
  _update_json=$$-update_tmp.json
  cat <<EOF > $_update_json
{
  "label": "$1",
  "lat": "${2:-0.0}",
  "lon": "${3:-0.0}",
  "_color": "$4"
}
EOF
  if [ -n "$4" ]; then
      sed -i 's/_color/color/' $_update_json
  fi
  echo -n "Adding/updating marker \"$1\"..."
  _curl_post marker $_update_json
  rm -f $_update_json
  echo "...done."
}

_remove_marker() {	# <label>
  _remove_json=$$-remove_tmp.json
  cat <<EOF > $_remove_json
{
  "label": "$1"
}
EOF
  echo -n "Removing marker \"$1\"..."
  _curl_post marker/remove $_remove_json
  rm -f $_remove_json
  echo "...done."
}

_get_markers() {
    curl "$_GEOM_URL/markers" | python3 -m json.tool
  echo "...done."
}

_clear_markers() {
    curl "$_GEOM_URL/markers/clear" | python3 -m json.tool
  echo "...done."
}

#set -x
