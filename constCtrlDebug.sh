#!/bin/bash

_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_dockerCreateOpts="--env SAT_DEBUG=enable"

source "$_DIR/constCtrl.sh"
