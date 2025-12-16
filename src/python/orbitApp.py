#!/usr/bin/env python3

# Description
#
#   Generates circular orbit for an equidistant satellite.

# Earth's characteristics (WGS 84)
#
#   Maximum (equatorial; Re) radius: 6,378.137 km
#   Minimum (polar; Rp) radius: 6,356.752314245 km

# Calculated orbits
#
#   Earth radius: sqrt ((Re * cos (latitude)) ** 2 + (Rp * sin (latitude)) ** 2)
#   Orbital circumference: <Earth radius> * cos (latitude)

# LEO characteristics
#
#   Satellites orbit around Earth with a period of 128 minutes or less
#   (making at least 11.25 orbits per day) and an eccentricity less
#   than 0.25.
#
#   Peak in number at an altitude around 800 km with a maximum
#   altitude of 2,000 kilometers (MEO minimum)

# Required Environment Variables
#
#  PLANE   (> 0, <= num-planes)
#  ORDINAL (> 0, <= num-sats)

# Configuration JSON
#
#    {
#        "num-planes": > 0; default: 1,
#        "num-sats": > 0; default: 1,
#        "inclination": >= -90.0 degrees, <= 90.0 degrees; default: 0.0;
#               a single value or comma-, colon-, or '..'-separated range
#               used when num-planes > 1,
#        "longitude": >= -180.0 degrees, <= 180.0 degrees; default: 0.0;
#               a single value or comma-, colon-, or '..'-separated range
#               used when num-planes > 1,
#        "plane-separation": longitudinal separation between planes (degrees;
#               default: None) centered around longitude'),
#        "altitude": > 200.0 km, < 2000.0 km; default: 800.0,
#        "time-multiplier": > 0.0; default: 1.0,
#        "real-time": boolean; default: false,
#        "start-time": [[<hh>:]<mm>:]<ss>; default: null,
#        "Q-endpoint": "http://10.100.100.100:16171/register",
#        "Q-ZMQ-pub": "tcp://10.100.100.100:12343",
#        "endpoint": [
#            "http://10.100.111.222:15052/api/marker"
#        ]
#    }

import argparse
import csv
import math
from   math import sqrt, fmod, hypot, radians, pi, isnan, isinf, dist
import threading
from   threading import Thread, RLock, Condition
import time

import numpy as np
from   pyproj import CRS, Transformer
import requests
from   scipy.spatial.transform import Rotation

from   jsonArgParse import JSONArgParse, altType, hhmmssType, incType, lonType, minFloatType, orbitAppArgs, endpointArgs

#############
# Constants #
#############

# WGS 84
_eMinRadius = 6356.752314245    # km
_eMaxRadius = 6378.137          # km

_g          = 9.80665           # m/s**2

_180deg     = 180.0
_180rad     = pi
_90deg      = 90.0
_90rad      = _180rad / 2.0
_270deg     = 270.0
_270rad     = _90rad + _180rad
_360deg     = 360.0
_360rad     = 2.0 * _180rad

#############
# Functions #
#############

sin     = lambda _d: math.sin (radians (_d))
cos     = lambda _d: math.cos (radians (_d))
eRadius = lambda _lat: hypot (_eMaxRadius * cos (_lat), _eMinRadius * sin (_lat))

# pyproj CRSs
# ECEF (Earth-Centered, Earth-Fixed) CRS
_ECEF_CRS = CRS.from_proj4 ("+proj=geocent +ellps=WGS84 +datum=WGS84")
# LLA (Latitude, Longitude, Altitude) CRS
_LLA_CRS  = CRS.from_proj4 ("+proj=latlong +ellps=WGS84 +datum=WGS84")

ECEF_to_LLA = Transformer.from_crs (_ECEF_CRS, _LLA_CRS,  always_xy = True)
LLA_to_ECEF = Transformer.from_crs (_LLA_CRS,  _ECEF_CRS, always_xy = True)

def _wrapLongitude (_lon: float, *_offsets: *[float]) -> float:
    for _offset in _offsets:
        _lon += _offset

    if  (_lon := fmod (_lon, _360deg)) > _180deg:
        _lon -= _360deg
    elif _lon < -_180deg:
        _lon += _360deg

    return _lon

class OrbitApp (JSONArgParse):

    def __init__ (self):
        super ().__init__ ()
        self._debug    = self._args.debug
        self._startC   = Condition ()    # start Condition
        self._threads  = dict ()         # _genOrbit threads; key: (iPlane, iSat, interval), val: <thread>
        self._rThreads = set ()          # running _genOrbit threads
        self._rLock    = RLock ()        # mutex for _threads, _rThreads, _debugFn, and _exfiltFn
        self._stopSet  = set ()          # threads to stop
        self.epArgs    = endpointArgs (self._args)

        self._debugFn  = dict ()         # errant 'debug' mode; key: <thread>, value: _writeGeoDict ()
        self._exfiltFn = dict ()         # 'exfilt' mode; key: <thread>, value: _exfiltrate ()

    def moreEpilogNotes (self):
        return ''

    def cliArgParser (self):

        _parser = argparse.ArgumentParser (formatter_class = argparse.RawDescriptionHelpFormatter,
                                           epilog = f'''
Notes
-----
  Examples:

   A single plane equatorial orbit with 7 satellites
     --num-sats 7

   2-plane polar orbit with 7 satellites per plane
     --num-planes 2
     --num-sats 7
     --inclination 90.0
     --longitude 0..90.0

   2-plane inclined orbits with 14 satellites per plane and time offset
     --num-planes 2
     --num-sats 14
     --inclination 44.0..55.0
     --longitude 0.0..35.0
     --start-time 18:00:00

  For the --format specification, the following fields will be replaced:
    plane
    ordinal
    num-sats
    num-planes

{self.moreEpilogNotes ()}
'''
                                           )
        _ = orbitAppArgs (_parser)

        _parser.add_argument ('-D', '--duration',
                              type    = hhmmssType,
                              help    = 'orbital duration ([[<hh>:]<mm>:]<ss>)')
        _parser.add_argument ('--inclination',
                              type    = incType,
                              default = (0.0, 0.0),
                              help    = 'orbit inclination (>= -90.0 degrees, <= 90.0 degrees; default: %(default)s), a single value or comma-, colon-, or \'..\'-separated range used when NUM_PLANES > 1')
        _parser.add_argument ('--longitude',
                              type    = lonType,
                              default = (0.0, 0.0),
                              help    = 'longitude (>= -180.0 degrees, <= 180.0 degrees; default: %(default)s), a single value or comma-, colon-, or \'..\'-separated range used when NUM_PLANES > 1')
        _parser.add_argument ('--plane-separation',
                              type    = incType,
                              help    = 'longitudinal separation between planes (degrees; default: %(default)s) centered around LONGITUDE')
        _parser.add_argument ('-A', '--altitude',
                              type    = altType,
                              default = 800.0,
                              help    = 'altitude (> 200.0 km, < 2000.0 km; default: %(default)s)')
        _parser.add_argument ('-T', '--time-multiplier',
                              type    = minFloatType,
                              default = 1.0,
                              help    = 'time multiplier (default: %(default)s)')
        _parser.add_argument ('-R', '--real-time',
                              action = 'store_true',
                              help   = 'add simulation time')
        _parser.add_argument ('--start-time',
                              type   = hhmmssType,
                              help   = 'start time ([[<hh>:]<mm>:]<ss>); default: %(default)s)')
        _parser.add_argument ('-F', '--format',
                              default = 'sat_{plane}_{ordinal}.csv',
                              help    = 'output file format (default: "%(default)s")')

        _parser.add_argument ('--info',
                              action = 'store_true',
                              help   = 'display diagnostic information')

        _parser.add_argument ('-d', '--debug',
                              action = 'store_true',
                              help   = argparse.SUPPRESS)

        return _parser

    def threadsWith (self, iPlane: int, iSat: int):
        _intThreads = list ()

        with self._rLock:
            for _tuple, _thread in self._threads.items ():
                if _tuple[0] == iPlane and _tuple[1] == iSat:
                    _intThreads.append (_thread)

        return _intThreads

    def startOrbit (self, _target, _numPlanes, _numSats):

        # Iterate over interval dict entries

        for _interval, _endpoint in self.epArgs.items ():
            _nvargs = {'interval': _interval,
                       'endpoint': _endpoint
                      }
            for _j in range (self._args.num_planes):
                _iPlane = _j + 1
                for _i in range (self._args.num_sats):
                    _iSat   = _i + 1
                    _thread = Thread (target = _target,
                                      name   = f'Gen node #{_iSat}',
                                      args   = (_iPlane, _iSat, _nvargs),
                                      daemon = True)
                    with self._rLock:
                        self._threads[(_iPlane, _iSat, _interval)] = _thread
                    _thread.start ()

        while len (self._rThreads) < len (self._threads):
            _debugPrint (f'Sleeping ({len (self._rThreads)} < {len (self._threads)})...')
            time.sleep (0.1)

    def startThreads (self, _args):
        # Tell all _genOrbits threads to start
        with self._startC:
            self._startC.notify_all ()

        # Join all threads in the list
        if _args.duration:
            for _t in self._threads.values ():
                _t.join ()
        else:
            while len (threading.enumerate ()) > 1 and len (self._threads) != len (self._stopSet):
                time.sleep (2.0)

    def setup (self):
        pass

    def debugPrint (self, *_vargs):
        if self._debug:
            print (*_vargs)

    ########
    # Main #
    ########

    def run (self):

        def _debugPrint (*_vargs):
            self.debugPrint (*_vargs)

        def _writeOrbit (_iPlane: int, _iSat: int, _kwargs: dict = {}):

            def _writeRow (_curTime: float, _lat: float, _lon: float, _alt: float, _delX: float, _delY: float, _delZ: float, _tDel: float) -> bool:
                _row = list ([_iPlane, _iSat])
                if _args.real_time:
                    _row += [time.time ()]
                _row += [_curTime, _lat, _lon, _alt]

                _csvOut.writerow (_row)

                return True

            _fName = _args.format.replace ('{plane}',      str (_iPlane))        \
                                 .replace ('{ordinal}',    str (_iSat))          \
                                 .replace ('{num-sats}',   str (_args.num_sats)) \
                                 .replace ('{num-planes}', str (_args.num_planes))

            try:
                with open (_fName, 'w', newline = '') as _fOut:
                    _csvOut  = csv.writer (_fOut)
                    _genOrbit (_iPlane, _iSat, _writeRow)
            except:     # ePerm
                pass

        def _publishOrbit (_iPlane: int, _iSat: int, kwargs: dict = {}):

            def _pubGeo (_time: float, _lat: float, _lon: float, _alt: float, _delX: float, _delY: float, _delZ: float, _tDel: float) -> bool:

                # Support multiple endpoints with different timing cadences

                _interval = kwargs.get ('interval', _args.interval)
                _d = {'label':    f'leosat-{_iPlane:02d}-{_iSat:02d}',
                      'plane':    _iPlane,
                      'ordinal':  _iSat,
                      'lat':      _lat,
                      'lon':      _lon,
                      'alt':      _alt,
                      'delx':     _delX,
                      'dely':     _delY,
                      'delz':     _delZ,
                      'time':     _time,
                      'interval': _interval}

                if _hil := kwargs.get ('hil'):
                    _d['color'] = f'bg-green-500'

                '''
                if _args.debug:
                    if _iSat == 1:
                        # https://tailscan.com/tailwind/backgrounds/background-color-class
                        _cName = ['cyan', 'teal', 'green'][(_iPlane - 1) % 3]
                        _d['color'] = f'bg-{_cName}-500'
                '''

                with self._rLock:
                    _cThread  = threading.current_thread ()
                    _debugFn  = self._debugFn .get (_cThread)
                    _exfiltFn = self._exfiltFn.get (_cThread)

                if   _debugFn and _exfiltFn:
                    _d['color'] = 'bg-pink-500'
                elif _debugFn:
                    _d['color'] = 'bg-yellow-500'
                elif _exfiltFn:
                    _d['color'] = 'bg-red-500'

                #_debugPrint (f'{_time}: {_d}')
                time.sleep (_tDel)

                for _ep in kwargs.get ('endpoint'):
                    try:
                        _ep   = _ep[0] if isinstance (_ep, tuple) else _ep
                        _resp = requests.post (_ep, json = _d)
                    except Exception as _e:
                        print (f'ERROR: @ {_time} {_d}: {_e}')
                        continue

                    try:
                        _resp.raise_for_status ()
                    except Exception as _e:
                        print (f'ERROR: @ {_time} {_d}: {_e} {_resp.json ()}')

                if _debugFn:
                    _debugFn  (self, _d)

                if _exfiltFn:
                    _exfiltFn (self, _d)

                return True

            _genOrbit (_iPlane, _iSat, _pubGeo, kwargs)

        # Generate CSV orbital data for a single satellite

        def _genOrbit (_iPlane: int, _iSat: int, _callback, _kwargs: dict = {}):

            def _lla_to_ecef (_lon: float, _lat: float, _alt: float):
                _xA, _yA, _zA = LLA_to_ECEF.transform ([_lon], [_lat], [_alt],
                                                       radians = False)
                return _xA[0], _yA[0], _zA[0]

            def _transformLLA (_lon: float, _lat: float, _alt: float):

                # Incline the orbital plane

                if _incDeg != 0.0:
                    _xA, _yA, _zA = _lla_to_ecef (_lon, _lat, _alt)
                    _v            = np.array ([_xA, _yA, _zA])
                    _vRot         = _rotInc.apply (_v) if _yA != 0.0 else _v

                    _lonA, _latA, _altA = ECEF_to_LLA.transform (_vRot[0:1], _vRot[1:2], _vRot[2:3], radians = False)

                    if isnan (_lonA[0].item ()) or isinf (_lonA[0].item ()):
                        print (f'ERROR: ({_iPlane} {_iSat} @ {_curTime}) {_v} {_vRot} -> {type (_repLon)} {_repLon} {_repLat} {_repRad}')
                        return None

                    _lon = _lonA[0].item ()
                    _lat = _latA[0].item ()
                    _alt = _altA[0].item ()

                # Offset the orbital plane

                _lon = _wrapLongitude (_lon, _lonOff, _rotLon)

                return _lon, _lat, _alt

            _lons = _args.longitude
            _incs = _args.inclination

            if _args.num_planes > 1:
                _incRng = _incs[1] - _incs[0]
                _incDeg = float (_iPlane - 1) * _incRng / float (_args.num_planes - 1) + _incs[0]
                _lonRng = _lons[1] - _lons[0]
                _lonOff = float (_iPlane - 1) * _lonRng / float (_args.num_planes - 1) + _lons[0]
            else:
                _incDeg = _incs[0]
                _lonOff = _lons[0]

            _rotInc = Rotation.from_euler ('x', radians (_incDeg))

            # Time sampling interval

            _interval = _kwargs.get ('interval', _args.interval)

            # Delta time and time sample distance (km)

            _delTime = _interval * _args.time_multiplier
            _delDist = _orbSpeed * _delTime

            # Baseline longitudinal delta

            _delLon = _360deg * _delDist / _orbDist

            # Longitudinal delta due to Earth's rotation

            _delRotL = _360deg * sin (_incDeg) * _interval * _args.time_multiplier / (24.0 * 60.0 * 60.0)
            #_debugPrint (f'({_iPlane} {_iSat}) _incDeg: {_incDeg}, _lonOff: {_lonOff}, _delLon: {_delLon}, _delRotL: {_delRotL}')

            _curLon = float (_iSat - 1) * _360deg / float (_args.num_sats)
            _rotLon = 0.0

            # Register this satellite interval thread and wait for start notification

            with self._startC:
                with self._rLock:
                    self._rThreads.add ((_iPlane, _iSat, _interval))

                _debugPrint (f'Node {_iPlane}/{_iSat}/{_interval}: waiting for notification...')
                self._startC.wait ()

            _debugPrint (f'Node {_iPlane}/{_iSat}/{_interval}: received notification; processing...')

            _doEP    = _kwargs.get ('endpoint') and (_tWant := _args.start_time)    # _args.start_time from CLI or ZMQ pub

            _cThread = threading.current_thread ()
            _curTime = 0.0
            _endTime = float (_args.duration) if _args.duration else None

            while (not _endTime or _curTime < _endTime) and _cThread not in self._stopSet:

                # Endpoint scheduling

                if _doEP:
                    _tNow = time.time ()
                    if (_tDel := _tNow - _tWant) < 0.0:
                        time.sleep (-_tDel)
                        continue        # wait for the future

                    _computeAndWrite = _tDel <= _interval
                else:
                    _computeAndWrite = True
                    _tDel            = _interval

                if _computeAndWrite:
                    _repLon  = _wrapLongitude (_curLon)
                    _repLat  = 0.0
                    _repRad  = (_eMaxRadius + _args.altitude) * 1000.0  # meters

                    _repLonV = _wrapLongitude (_repLon, 5.0)    # tangential line
                    _repLatV = _repLat
                    _repRadV = _repRad * cos (radians (5.0))

                    # Transform the LLA

                    if _repLLATuple := _transformLLA (_repLon, _repLat, _repRad):
                        _repLon, _repLat, _repRad = _repLLATuple
                        _xA, _yA, _zA             = _lla_to_ecef (_repLon, _repLat, _repRad)
                    else:
                        break

                    # Transform velocity vector endpoint

                    if _repLLAVTuple := _transformLLA (_repLonV, _repLatV, _repRadV):
                        _repLonV, _repLatV, _repRadV = _repLLAVTuple
                        _xVA, _yVA, _zVA             = _lla_to_ecef (_repLonV, _repLatV, _repRadV)
                    else:
                        break

                    # Calculate velocity vector

                    _vDist = dist ([_xA, _yA, _zA], [_xVA, _yVA, _zVA])     # Euclidean distance for normalization

                    _dX = _orbSpeed * (_xVA - _xA) / _vDist
                    _dY = _orbSpeed * (_yVA - _yA) / _vDist
                    _dZ = _orbSpeed * (_zVA - _zA) / _vDist

                    # Write record

                    if not _callback (_curTime, _repLat, _repLon, _repRad / 1000.0 - _eMaxRadius, _dX, _dY, _dZ, _tDel):
                        break

                # Increment time, distance, and baseline longitude

                _tWant   += _interval
                _curTime += _interval
                _curLon   = _wrapLongitude (_curLon, _delLon)
                _rotLon  += _delRotL

            self.stoppedThread (_iPlane, _iSat, _interval)

        _args = self._args

        self.setup ()

        # Gravitational force equation: F = m · g
        # Orbital force equation:       F = m · v**2 / r
        #
        # Thus, g = v**2 / r  ->  v = sqrt (g · r)

        # Orbital speed (kps) with equatorial orbit as reference

        _orbSpeed = sqrt (_g * (_args.altitude + _eMaxRadius) * 1000.0) / 1000.0

        # Orbital distance (km)

        _orbDist = _360rad * (_args.altitude + _eMaxRadius)

        # Inter-satellite displacement (km)

        _satDist = _orbDist / _args.num_sats

        if _args.info:
            print (f'Information\n  tangential speed (kps): {_orbSpeed}\n  orbital distance (km): {_orbDist}\n  inter-satellite displacement (km): {_satDist}')

        _target = _publishOrbit if _args.endpoint else _writeOrbit
        self.startOrbit (_target, _args.num_planes, _args.num_sats)

        _debugPrint ("Main thread: all threads started.")

        self.startThreads (_args)

        _debugPrint ("Main thread: all threads finished.")

    def stoppedThread (self, _iPlane: int, _iSat: int, _interval: float):
        pass

if __name__ == '__main__':
    _orbitApp = OrbitApp ()
    _orbitApp.run ()
