#!/usr/bin/env python3

import argparse
from   threading import Thread, Event
import os       # .path.isdir (), .path.exists ()
import re       # .compile ()
import sys      # .path
from   typing import override

import ZmqSubscriber
from   ZmqPPWrapper import ZmqPPWrapperType

from   jsonArgParse import JSONArgParse, inRangeType, rangeType, zmqPubSubArgs, orbitAppArgs, hilArgs

for _path in ('bns/src', 'bns.git/src'):
    if os.path.isdir (_path):
        sys.path.insert (0, _path)

import main as bns


def _getIPAddress ():   # get container IP address from /proc file system
    _FIB_TRIE = '/proc/net/fib_trie'
    _IP_RE    = re.compile (r'^\|-- (?P<ip>[0-9.]+)$')

    if os.path.exists (_FIB_TRIE):
        with open (_FIB_TRIE, 'r') as _fIn:
            _ipSet    = set ()
            _lastLine = ''
            for _line in _fIn:
                _line = _line.strip ()
                if _line.find ('/32 host LOCAL') != -1:
                    # Process last line as IP address but ignore localhost
                    if (_match := _IP_RE.match (_lastLine)) and \
                       (_ip := _match.group ('ip')) and\
                       _ip != '127.0.0.1':
                        _ipSet.add (_ip)
                else:
                    _lastLine = _line

            _maxIp = None
            while _ipSet:
                _ip = _ipSet.pop ()
                if _maxIp is None or _ip > _maxIp:
                    _maxIp = _ip

            return f'{_maxIp}/16' if _maxIp else None

    return None

class ThirdPartyApp (JSONArgParse):

    def __init__ (self):
        super ().__init__ ()
        self._iPlane     = None         # populated by run ()
        self._iSat       = None         # (same as above)
        self._q_endpoint = None         # populated by setup () and referenced by startOrbit ()
        self._zmq_start  = Event ()     # accessed by startThreads () and provisionally set by _zmqSubCB ()
        self._stop       = Event ()     # signal thread termination

    @override
    def cliArgParser (self):
        _cliParser = bns.getargparser ()
        _ = zmqPubSubArgs (_cliParser)
        _ = orbitAppArgs  (_cliParser)
        _cliParser.add_argument ('-d', '--debug',
                                 action = 'store_true',
                                 help   = argparse.SUPPRESS)
        return _cliParser

    @override
    def moreArgs (self):        # add Target
        if _ipAddr := _getIPAddress ():
            return [_ipAddr]
        else:
            return list ()

    def debugPrint (self, *_vargs):
        if self._args.debug:
            print (*_vargs)

    def _zmqSubCB (self, _topic, _msg):

        def _checkPlaneOrdinal ():

            # Optional plane number or range

            if ((_iPlane := _msg.get ('plane')) is None) or \
               ((_iPTuple := rangeType (_iPlane, 1, self._args.num_planes, _raise = False)) and \
                inRangeType (self._iPlane, *_iPTuple, _openRange = False, _raise = False)):

                # Optional satellite number or range

                if ((_iSat := _msg.get ('ordinal') if _iPlane else None) is None) or \
                   ((_iSTuple := rangeType (_iSat, 1, self._args.num_sats, _raise = False)) and \
                    inRangeType (self._iSat, *_iSTuple, _openRange = False, _raise = False)):
                    return True

            return False

        def _checkClass ():
            return ((_appClass := _msg.get ('class')) is None) or _appClass == 'thirdParty'

        self.debugPrint (_topic, _msg)

        if not _checkPlaneOrdinal ():
            self.debugPrint ('Inapplicable message.')
            return

        # Start run ()

        if _topic == 'thirdParty':
            self._zmq_start.set ()

        # Stop run ()

        elif _topic == 'stop' and _checkClass ():
            self._stop.set ()

    @override
    def run (self):
        if (_HZN_NODE_ID := os.getenv ('HZN_NODE_ID')) and \
           (_hilArgs := hilArgs (self._args)) and \
           (_planeOrdinal := _hilArgs.get (_HZN_NODE_ID)):
            _sPlane, _sSat = _planeOrdinal
            try:
                self._iPlane = inRangeType (_sPlane, 1, self._args.num_planes, _openRange = False)
                self._iSat   = inRangeType (_sSat,   1, self._args.num_sats,   _openRange = False)
            except Exception as _e:
                print (f'ERROR: {_e}')
                sys.exit (1)
        else:
            print (f'ERROR: bad or missing HZN_NODE_ID environment variable!')
            sys.exit (1)

        # ZMQ subscription
        _zmqSub = ZmqSubscriber.ZmqSubscriber (None,
                                               self._args.Q_ZMQ_pub,
                                               '',
                                               self._zmqSubCB,
                                               ZmqPPWrapperType.JSON,
                                               False)
        _thread = Thread (target = lambda: _zmqSub.run (),
                          name   = 'ZMQ subscriber',
                          daemon = True)
        _thread.start ()

        while not self._stop.is_set ():

            # Wait for ZMQ start notification or stop notification
            while not self._zmq_start.wait (2.0):
                if self._stop.is_set ():
                    sys.exit (0)

            self._zmq_start.clear ()    # manually repeat

            try:
                bns.run (self._args)        # one-shot
            except:     # ePerm
                pass


if __name__ == '__main__':
    _thirdApp = ThirdPartyApp ()
    _thirdApp.run ()
