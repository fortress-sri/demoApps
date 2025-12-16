#!/usr/bin/env python3

import os
import re
import sys


# Decode little-endian hex-encoded IP address

def _decodeAddr (_addr):
    if int (_addr, 16):
        _str    = _addr
        _octets = []
        for _ in range (4):
            _idx = len (_str) - 2
            _o   = _str[_idx: ]
            _str = _str[: _idx]
            _octets.append (str (int (_o, 16)))

        _ipstr = '.'.join (_octets)
    else:
        _ipstr = 'any'

    return _ipstr.rjust (15)

# Decode big-endian (network-ordered) port number

def _decodePort (_port):
    return str (int (_port, 16)).ljust (5)


if len (sys.argv) > 1:
    _file = sys.argv[1]
else:
    _file = '/proc/net/tcp'

if not os.path.exists (_file):
    print ('ERROR: "{}" does not exist'.format (_file))
    sys.exit (1)


_ADDR_RE = re.compile (r'(?P<hex_host>[0-9A-F]{8}):(?P<hex_port>[0-9A-F]{4})')


with open (_file, 'r') as proc_net:
    for _line in proc_net:
        # Trim trailing whitespace from input line
        _line  = re.sub (r'\s*$', '', _line)

        # Look for two hexadecimal address:port pairs

        _addrs = []     # tokenized input line
        _idx   = 0      # next search index
        for _i in range (2):
            _m = _ADDR_RE.search (_line, _idx)
            if _m:
                if not _i:
                    _addrs.append (_line[: _m.start ('hex_host') - 1])  # line prefix

                _addrs.append ('{}:{}'.format (_decodeAddr (_m.group ('hex_host')),
                                               _decodePort (_m.group ('hex_port'))))
                _idx = _m.end ('hex_port')
            else:
                _addrs = None   # failed to find addr/port pair
                break

        # Reconstitute line with substitutions

        if _addrs:
            _addrs.append (_line[_idx + 1:])    # line suffix
            _line = ' '.join (_addrs)

        # Provisionally modify the header line

        else:
            _parts = _line.split (' ')
            if 'sl' in _parts:
                _off   = _parts.index ('sl')
                _parts[1 + _off] = '    '               # padding before 'local_address'
                _parts[4 + _off] = '  '                 # padding after 'rem_address'
                _parts.insert (3 + _off, '         ')   # padding between 'local_address' and 'rem_address'
                _line = ' '.join (_parts)

        print (_line)
