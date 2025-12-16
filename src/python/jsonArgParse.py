import argparse
import json
import os       # .getenv (), .path.isfile ()
import socket   # .gethostbyname ()
import sys      # .exit ()
from   urllib.parse import urlparse


#########################
# Custom argparse types #
#########################

def inRangeType (_v, _min, _max, _openRange = True, _raise = True):   # open (cf., closed) range check
    if not isinstance (_v, type (_min)):
        _v = type (_min) (_v)
    if _openRange:
        if _min < _v and _v < _max:
            return _v
    else:
        if _min <= _v and _v <= _max:
            return _v
    if _raise:
        raise argparse.ArgumentTypeError (f"{_v} not in {'open' if _openRange else 'closed'} range ({_min}..{_max})")
    else:
        return None

def rangeType (_v, _min, _max, _ordered = True, _openRange = False, _raise = True) -> tuple:
    _vals = list ()

    if isinstance (_v, str):
        for _sep in (', ', ': ', ',', ':', '..', ' '):
            if len (_parts := _v.split (_sep)) == 2:
                break

        for _part in _parts:
            if (_val := inRangeType (_part, _min, _max, _openRange, _raise)) is None:
                return None
            _vals.append (_val)
    else:
        if (_val := inRangeType (_v, _min, _max, _openRange, _raise)) is None:
            return None
        _vals.append (_val)

    _lVals = len (_vals)

    if   _lVals == 1:
        _vals.append (_vals[0])
    elif _lVals > 2 or (_ordered and _vals[0] > _vals[1]):
        if _raise:
            raise argparse.ArgumentTypeError (f"{_v} not in {'open' if _openRange else 'closed'} range ({_min}..{_max})")
        else:
            return None

    return tuple (_vals)

def minType (_v, _min, _raise = True):
    if type (_v) != type (_min):
        _v = type (_min) (_v)
    if _v >= _min:
        return _v
    if _raise:
        raise argparse.ArgumentTypeError (f'{_v} < {_min}')
    else:
        return None

def minIntType (_s: str, _min: int = 0) -> int:
    return minType (_s, _min)

def minFloatType (_s: str, _fmin: float = 0.0, _raise = True) -> float:
    return minType (_s, _fmin, _raise)

def latType (_lat: str) -> float:
    return inRangeType (_lat, -90.0, 90.0)

def lonType (_lon: str) -> tuple:              # orbit starting longitude range
    return rangeType (_lon, -180.0, 180.0, _ordered = False)

def incType (_sInc: str) -> tuple:             # orbit inclination range
    return rangeType (_sInc, -90.0, 90.0)

def numSatType (_nSat: str) -> int:
    return minIntType (_nSat, 1)

def altType (_alt: str) -> float:
    return inRangeType (_alt, 200.0, 2000.0)

def hhmmssType (_s: str, _raise = True) -> int:
    _parts  = _s.split (':')
    if (_lParts := len (_parts)) > 3:
        if _raise:
            raise argparse.ArgumentTypeError (f'bad duration ("{_s}")')
        else:
            return None

    _iTime = 0
#    _sTime = ''

    for _i, _spec in enumerate ([(60, ), (60, 0, 59), (1, 0, 59)][3 - _lParts:]):
        if (_t := int (_parts.pop (0))) < 0:
            raise argparse.ArgumentTypeError (f'bad duration ("{_s}")')

        # Provisionally check range
        if _i and len (_spec) == 3:
            _ = inRangeType (_t, _spec[1], _spec[2], False)

        _iTime = (_iTime + _t) * _spec[0]
#        _sTime = f'({_sTime} + {_t}) * {_spec[0]}' if _sTime else f'{_t} * {_spec[0]}'

#    print (f'{_s} -> {_sTime} = {_iTime} seconds')

    return _iTime

def fileType (_file: str) -> str:
    if os.path.isfile (_file):
        return _file
    else:
        argparse.ArgumentTypeError (f'file not found ("{_file}")')

def _endpointType (_ep: str, _scheme: str) -> tuple:
    _pResult = urlparse (_ep)
    if _pResult.scheme == _scheme and _pResult.netloc:
        if len (_epParts := _pResult.netloc.split (':')) == 2:
            try:
                # Validate hostname or IPv4 address
                _host = socket.gethostbyname (_epParts[0])

                # Validate registered port range
                _port = inRangeType (_epParts[1], 1024, 49151, _openRange = False)

                return _ep, _host, _port
            except Exception as _e:
                raise argparse.ArgumentTypeError (f'invalid "{_scheme}" endpoint ("{_ep}"; {_e})')

    raise argparse.ArgumentTypeError (f'invalid "{_scheme}" endpoint ("{_ep}")')

def httpEndpoint (_ep: str, _wantTuple = False) -> str | tuple:
    _epTuple = _endpointType (_ep, 'http')
    #print (f'HTTP endpoint: {_epTuple}')
    return _epTuple if _wantTuple else _epTuple[0]

def tcpEndpoint (_ep: str, _wantTuple = False) -> str | tuple:
    _epTuple = _endpointType (_ep, 'tcp')
    #print (f'TCP endpoint: {_epTuple}')
    return _epTuple if _wantTuple else _epTuple[0]

def timedHTTPEndpoint (_ep: str, _raise = True) -> str | tuple:
    _epParts = _ep.split (',')
    _lEPParts = len (_epParts)
    #print (f'timed HTTP endpoint: {_epParts}/{_lEPParts}')
    if _lEPParts <= 2:
        _host = httpEndpoint (_epParts[0])
        if _lEPParts == 2:
            return (_host, minType (_epParts[1], 0.0))
        else:
            return _host
    else:
        if _raise:
            raise argparse.ArgumentTypeError (f'invalid timed HTTP endpoint ("{_ep}")')
        else:
            return None

def hilType (_hil: str, _raise = True) -> tuple:
    _hilParts = _hil.split ('|')    # <key>|<value>
    if len (_hilParts) == 2:
        _hilList = list ()
        _hilList.append (_hilParts[0].strip ())

        _poParts = _hilParts[1].split (',') # <ordinal> | (<plane>,<ordinal>)
        if (_lPO := len (_poParts)) <= 2:
            if _lPO == 1:   # ordinal only; plane: 1
                _hilList.append (1)

            for _part in _poParts:
                try:
                    _hilList.append (int (_part.strip ()))
                except:
                    break

            if len (_hilList) == 3:
                return tuple (_hilList)     # host, plane, ordinal

    if _raise:
        raise argparse.ArgumentTypeError (f'invalid HIL ("{_hil}")')
    else:
        return None

def endpointArgs (_args) -> dict:
    def _addEndpoint (_ep, _interval: float = None):
        if not _interval:
            _interval = _args.interval

        if not (_intList := _epDict.get (_interval)):
            _intList = list ()
            _epDict[_interval] = _intList

        _intList.append ((_ep, _interval))

    _epDict = dict ()
    for _ep in _args.endpoint:
        if   isinstance (_ep, str):
            _addEndpoint (_ep)

        elif isinstance (_ep, tuple):
            _addEndpoint (_ep[1], _ep[0])

    return _epDict

def hilArgs (_args) -> dict:
    _hilDict = dict ()
    for _hil in _args.HIL:
        if isinstance (_hil, tuple):
            _hilDict[_hil[0]] = _hil[1:]

    return _hilDict

def orbitAppArgs (_cliParser):
    _cliParser.add_argument ('-N', '--num-sats',
                             type     = numSatType,
                             help     = 'number of satellites (> 0)',
                             required = True)
    _cliParser.add_argument ('--num-planes',
                             type     = minIntType,
                             default  = 1,
                             help     = 'number of orbital planes (> 0; default: %(default)s)')
    _cliParser.add_argument ('-I', '--interval',
                             type     = minFloatType,
                             default  = 10.0,
                             help     = 'sample interval in seconds (default: %(default)s)')
    _cliParser.add_argument ('-E', '--endpoint',
                             type     = timedHTTPEndpoint,
                             action   = 'append',
                             help     = 'Position application REST API endpoint (default: "%(default)s")')
    _cliParser.add_argument ('-H', '--HIL',
                             type     = hilType,
                             action   = 'append',
                             help     = 'Hardware-In-the-Loop (default: "%(default)s")')

    return _cliParser

def zmqPubSubArgs (_cliParser):
    _cliParser.add_argument ('--Q-ZMQ-pub',
                             type     = tcpEndpoint,
                             required = True,
                             help     = 'Q controller ZMQ coordination endpoint (example: "tcp://10.100.100.100:12343")')

    return _cliParser

def satAppArgs (_cliParser):
    _cliParser.add_argument ('--Q-endpoint',
                             type     = httpEndpoint,
                             required = True,
                             help     = 'Q controller satellite registration endpoint (example: "http://10.100.100.100:16171/nodes")')
    _ = zmqPubSubArgs (_cliParser)

    return _cliParser

class JSONArgParse:
    def __init__ (self):
        self._args = self._getCLIArgs () if os.getenv ('CLI', None) else self._getJSONArgs ()

    def _getCLIArgs (self):
        _cliParser = self.cliArgParser ()
        return _cliParser.parse_args ()

    def moreArgs (self):
        return list ()

    def _getJSONArgs (self):

        _parser = argparse.ArgumentParser (formatter_class = argparse.RawDescriptionHelpFormatter,
                                           epilog = f'''
Notes
-----
  Optional Environment Variable:

    CLI      when defined, obtain configuration from command line;
             otherwise read from specified JSON file
'''
                                           )
        _parser.add_argument ('JSON',
                              type = fileType,
                              help = 'constellation definition JSON file')

        _args = _parser.parse_args ()
        try:
            _cliParser = self.cliArgParser ()
            _options   = dict ()
            for _action in _cliParser._actions:
                if (_tAction := type (_action)) in (argparse._HelpAction, argparse._StoreAction,
                                                    argparse._StoreTrueAction, argparse._StoreFalseAction,
                                                    argparse._AppendAction):
                    for _option in _action.option_strings:
                        _options[_option] = _tAction

            with open (_args.JSON, 'r') as _jIn:
                _jDict = json.load (_jIn)

            _argList = list ()
            for _k, _v in _jDict.items ():
                for _dash in ('-', '--'):
                    _dashK = f'{_dash}{_k}'

                    if _tAction := _options.get (_dashK):
                        if   _tAction is argparse._StoreAction:
                            if isinstance (_v, list):
                                for _ve in _v:
                                    _argList += [_dashK, str (_ve)]

                            else:
                                _argList += [_dashK, str (_v)]

                        elif _tAction is argparse._AppendAction and _v:
                            if   isinstance (_v, list):
                                for _ve in _v:
                                    _argList += [_dashK, str (_ve)]

                            elif isinstance (_v, dict):
                                for _vk, _vv in _v.items ():
                                    if   isinstance (_vv, list):
                                        for _vve in _vv:
                                            _argList += [_dashK, f'{_vk}|{_vve}']

                                    elif isinstance (_vv, (str, int, float)):
                                        _argList += [_dashK, f'{_vk}|{_vv}']

                            elif isinstance (_v, str):
                                _argList += [_dashK, _v]

                        elif _tAction in (argparse._HelpAction, argparse._StoreTrueAction,
                                          argparse._StoreFalseAction) and _v:
                            _argList += [_dashK]

            _argList += self.moreArgs ()

            return _cliParser.parse_args (_argList)

        except Exception as _e:
            print (f'ERROR: {_e}')
            sys.exit (1)

    def moreEpilogNotes (self):
        return ''

    def cliArgParser (self):
        raise Exception ('*** subclass must override this method')
