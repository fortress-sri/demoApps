#!/usr/bin/env python3

import argparse
from   datetime import datetime, timezone
from   http import HTTPStatus
from   io import StringIO
import json
import logging          # .getLogger (), .Formatter (), .FileHandler ()
import os               # .path
import requests
import signal
import sys
import time
from   threading import Thread
from   typing import override
import socket

from   flask import Flask, abort, request

from   ZmqPublisher  import ZmqPublisher
from   ZmqSubscriber import ZmqSubscriber
from   ZmqPPWrapper  import ZmqPPWrapperType

# CLI arg parsing and server invocation

from   jsonArgParse import JSONArgParse, inRangeType, minFloatType, rangeType, httpEndpoint, tcpEndpoint, endpointArgs, orbitAppArgs, satAppArgs, hilArgs

###########
# Globals #
###########

_main_path = os.path.abspath(str(sys.modules['__main__'].__file__))
_base_path = os.path.basename(_main_path)
_base_name, _ = os.path.splitext(_base_path)

_logger = logging.getLogger(_base_name)

del _, _main_path, _base_path

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]


class FlaskQController (JSONArgParse):

    class _ZMQueuePub():

        def __init__(self, host, zmqPubOpt, zmq_pub):
            endpoint = f'tcp://{host}:{zmq_pub}'
            self._zmq_pub = ZmqPublisher(None, endpoint, '', ZmqPPWrapperType.JSON)

            self._zmq_pub.run (f'ZMQ {zmqPubOpt} Msg Publication')

            _logger.info(f'Started ZeroMQ {zmqPubOpt} publication thread ({endpoint})')

        def queue_message(self, obj, topic=None):
            if self._zmq_pub:
                self._zmq_pub.queue_message(obj, topic)

        def terminate(self):
            if self._zmq_pub:
                self._zmq_pub.terminate()

    class _ZMQueueSub(ZmqSubscriber):
        def __init__(self, zmqSubOpt, zmqSubEP, zmqSubCb):
            super().__init__(None, zmqSubEP, '', zmqSubCb, ZmqPPWrapperType.JSON, False)

            _thread = Thread(target=self.run,
                             name=f'ZMQ {zmqSubOpt} Msg Subscription',
                             args=(),
                             daemon=True)
            _thread.start()

            _logger.info(f'Started ZeroMQ {zmqSubOpt} subscription thread ({zmqSubEP})')

    # https://stackoverflow.com/questions/5160077/encoding-nested-python-object-in-json

    class _AsJSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if hasattr(obj, 'asJSON'):
                return obj.asJSON()
            else:
                return json.JSONEncoder.default(self, obj)

    @staticmethod
    def _get_member(content, key, cls=str):
        member = content[key] if key in content else None
        error = None
        if member:
            if not isinstance(member, cls):
                try:
                    member = cls(member)
                except:
                    error = TypeError(f'wanted {cls} but have {member.__class__}')

        return (member, error)

    @staticmethod
    def _datetime_to_posix(_dt=None):
        if _dt is None:
            _dt = datetime.now(tz=timezone.utc)
        return _dt.timestamp()

    @classmethod
    def _posix_now(cls):
        return cls._datetime_to_posix()

    @staticmethod
    def _convert_to_bytes(arg):
        return arg if isinstance(arg, bytes) else bytes(arg, 'utf-8')

    @staticmethod
    def _get_post_dict():
        try:
            content = request.get_json(force=True)

            return content if isinstance(content, dict) else None
        except Exception as _e:
            abort(HTTPStatus.BAD_REQUEST, 'Bad JSON input')

    @classmethod
    def _get_rest_dict(cls, *args):
        _dict = dict(request.args)

        _pDict = dict()
        for _k, _v in _dict.items():
            if isinstance(_v, list) and len(_v) == 1:
                _pDict[_k] = _v[0]

        _dict.update(_pDict)

        cls._cast_values(_dict, *args)

        if request.method == 'POST':
            try:
                _pDict = request.get_json(force=True)

                if isinstance(_pDict, dict):
                    _dict.update(_pDict)
            except:
                pass

        return _dict

    # Cast selected dict values from string to supplied type
    # Usage: <type>, <key name>, ... [<type>, <key name>, ...]

    @staticmethod
    def _cast_values(_restDict, *args):
        for _arg in args:

            # Look for <type>

            if isinstance(_arg, type):
                _type = _arg
                continue

            # Cast specified key

            _val = _restDict.get(_arg)
            if _val is not None:

                # Iterate through each list element

                if isinstance(_val, list):
                    _vList = list()
                    for _v in _val:
                        _vList.append(_type(_v))
                    _val = _vList

                # Singleton

                else:
                    _val = _type(_val)

                _restDict[_arg] = _val

        return _restDict

    @staticmethod
    def _get_values(_dict, *args):
        _values = list()

        for _arg in args:
            if _arg in _dict:
                _values.append(_dict[_arg])
            else:
                return list()  # required key is missing

        return _values

    @staticmethod
    def _restAPIJSON(_rStatus: requests.Response) -> tuple:
        _sCode = _rStatus.status_code
        _rJSON = None
        if _sCode == requests.codes.ok:
            try:
                _rJSON = _rStatus.json()
            except:
                pass

        return _rJSON, _sCode

    @staticmethod
    def _makeURI(host: str, bPort: int, endPoint: str) -> str:
        return os.path.join(f'http://{host}:{bPort}', endPoint)

    def restAPIGet(self, host: str, bPort: int, endPoint: str, **kwargs) -> tuple:
        _uri = self._makeURI(host, bPort, endPoint)
        return self._restAPIJSON(requests.get(_uri, params=kwargs if kwargs else None))

    def restAPIPost(self, host: str, bPort: int, endPoint: str, payload) -> tuple:
        _uri = self._makeURI(host, bPort, endPoint)
        return self._restAPIJSON(requests.post(_uri, json=payload))

    def restAPIPut(self, host: str, bPort: int, endPoint: str, payload) -> tuple:
        _uri = self._makeURI(host, bPort, endPoint)
        return self._restAPIJSON(requests.put(_uri, json=payload))

    def restAPIDelete(self, host: str, bPort: int, endPoint: str, payload) -> tuple:
        _uri = self._makeURI(host, bPort, endPoint)
        return self._restAPIJSON(requests.delete(_uri, json=payload))

    def _debug_report(self, topic, content):
        _logger.debug(f'{topic} {content}')

    # https://docs.python.org/3.3/whatsnew/3.0.html?highlight=execfile#builtins
    def evalStream(self, _stream, _evalDict=None, _file=__file__):
        try:
            if _evalDict is None:
                _evalDict = dict()

            # https://stackoverflow.com/questions/39647566/why-does-python-3-exec-fail-when-specifying-locals
            _globals = dict(globals())

            _globals['__file__'] = _file

            _fParts = os.path.basename(_file).split('.')
            _globals['__name__'] = f'__{_fParts[0]}__'

            _globals['evalDict'] = _evalDict  # returned JSON values

            _globals['__svr__'] = self  # permit internal state access

            exec(_stream.read(), _globals)

        except SyntaxError as err:
            _evalDict[self._KEY_DERROR] = f'{_file} failed with {err}'

        except Exception as xcep:
            _evalDict[self._KEY_DERROR] = f'{_file} failed with {xcep}'

        return _evalDict

    def evalFile(self, _pyFile, _evalDict=None):
        if os.path.isfile(_pyFile):
            with open(_pyFile, 'r') as _fIn:
                return self.evalStream(_fIn, _evalDict, _pyFile)
        else:
            return {self._KEY_DERROR: f'Could not evaluate "{_pyFile}": file not found'}

    @override
    def cliArgParser (self):
        _cliParser = argparse.ArgumentParser ()

        _ = orbitAppArgs (_cliParser)
        _ = satAppArgs   (_cliParser)

        _cliParser.add_argument ('--log-level',
                                 help = 'logger level (e.g., "DEBUG", "INFO", etc.)')
        _cliParser.add_argument ('--tee-log',
                                 help = 'optional logging path')

        _cliParser.add_argument ('-d', '--debug',
                                 action = 'store_true',
                                 help   = argparse.SUPPRESS)

        return _cliParser

    def __init__(self):
        super ().__init__ ()

        self.flask      = Flask (__name__)
        self._debug     = self._args.debug
        self.satInts    = dict ()
        self.epArgs     = endpointArgs (self._args)
        self.totSatInts = self._args.num_planes * self._args.num_sats * len (self.epArgs)
        self.lastStart  = None          # initial start time for restarted processes
        self.hilArgs    = hilArgs (self._args)

        if self._debug:
            _logger.info('*** DEBUG MODE ***')

        # Configure logger

        if self._args.log_level:
            _logLevel = getattr(logging, self._args.log_level.upper(), None)
            if _logLevel is not None:
                _logger.setLevel(_logLevel)
            else:
                _logger.warning(f'Invalid --log-level ({self._args.log_level})')

        # Per https://stackoverflow.com/questions/13733552/logger-configuration-to-log-to-file-and-print-to-stdout

        _logFormatter  = logging.Formatter(fmt='%(asctime)s %(levelname)s: %(message)s', datefmt='[%d/%b/%Y %H:%M:%S]')
        _stdOutHandler = logging.StreamHandler()
        _stdOutHandler.setFormatter(_logFormatter)

        _logger.addHandler(_stdOutHandler)

        if self._args.tee_log:
            if os.path.isfile(self._args.tee_log):
                _tee_log = self._args.tee_log
            elif os.path.isdir(self._args.tee_log):
                _tee_log = os.path.join(self._args.tee_log, f'{_base_name}.log')
            else:
                _tee_log = None

            if _tee_log:
                _logger.info(f'logging to "{_tee_log}"')

                _fileHandler = logging.FileHandler(_tee_log)
                _fileHandler.setFormatter(_logFormatter)
                _logger.addHandler(_fileHandler)
            else:
                _logger.warning(f'Invalid --tee-log ("{self._args.tee_log}")')

        # Define SIGTERM signal handler

        signal.signal(signal.SIGTERM, lambda _signum, _frame: self._shutdown(True))
        signal.signal(signal.SIGINT,  lambda _signum, _frame: self._shutdown(True))

    def _return_response(self, _obj, _status, _cvtContent, _mType):
        return self.flask.response_class(
            response = _cvtContent(_obj),
            status   = _status,  # specific HTTPStatus.*
            mimetype = _mType
        )

    def _return_json_response(self, _ret_obj, _ret_status):

        # Provisionally log errors
        if _ret_status != HTTPStatus.OK or isinstance(_ret_obj, str):
            if _ret_status != HTTPStatus.OK:
                _level = 'WARNING'
                _msg   = f'{_ret_status}: {_ret_obj}'
            else:
                _level = None
                _msg   = None

            if isinstance(_ret_obj, str):
                _m = self._RE_LOG_PATTERN.match(_ret_obj)
                if _m:
                    _level = _m.group('level')
                    _msg   = _m.group('msg')

            if _msg:
                _logger.log(getattr(logging, _level), _msg)

        return self._return_response(_ret_obj, _ret_status,
                                     lambda _cnt: json.dumps(_cnt, cls=self._AsJSONEncoder),
                                     'application/json')

    def _return_text_response (self, _obj, _status):
        if isinstance (_obj, list):
            _cvtContent = lambda _cnt: '\n'.join (_cnt)
        else:
            _cvtContent = lambda _cnt: str (_cnt)
        return self._return_response (_obj, _status, _cvtContent, 'text/plain')

    def _return_image_response(self, _obj, _status, _iType):
        return self._return_response(_obj, _status, lambda _cnt: _cnt, f'image/{_iType}')

    def _queue_message(self, obj, topic=None):
        if self._zmq_pub:
            self._zmq_pub.queue_message(obj, topic)

    #############
    # Endpoints #
    #############

    # /nodes/<action> POST/GET endpoint

    def _nodes_action (self, action: str):

        def _satIntStatus (verbose = False) -> tuple:
            if  (_numSatInts := len (self.satInts)) == self.totSatInts:
                _msg = f'INFO: All {self.totSatInts} ' \
                       'satellite intervals are registered.' if verbose else \
                       'OK'
            elif _numSatInts:
                _msg = f'WARNING: only {_numSatInts} of {self.totSatInts} ' \
                       'satellite intervals are registered.'
            else:
                _msg = f'WARNING: No satellite intervals out of {self.totSatInts} ' \
                       'are registered.'

            return _numSatInts, _msg

        def _handleStop ():
            
            def _pruneSatTuple ():
                _delList = list ()
                for _satTuple in self.satInts.keys ():
                    if (_satTuple[0] == _iPlane) and ((_iSat is None) or (_satTuple[1] == _iSat)):
                        _delList.append (_satTuple)

                for _delTuple in _delList:
                    del self.satInts[_delTuple]

            if (_hStatus := _checkPlaneOrdinal ()) != HTTPStatus.OK:
                return self._return_text_response (f'Bad plane/ordinal ({_pDict})', _hStatus)

            _numSatInts, _msg = _satIntStatus ()

            if _numSatInts:

                # Stop specified or all nodes

                if ((_appClass := _pDict.get ('class')) is None) or _appClass == 'sat':
                    if _iPlane := _pDict.get ('plane'):
                        _iSat = _pDict.get ('ordinal')
                        _pruneSatTuple ()
                    else:
                        self.satInts.clear ()
        
                    if len (self.satInts) == 0:
                        self.lastStart = None

                    self._queue_message (_pDict, 'stop')

                # Stop all HIL nodes

                elif _appClass.lower () == 'hil':
                    _pDict['class'] = 'sat'
                    for _hk, _hv in self.hilArgs.items ():
                        _iPlane = _hv[0]
                        _iSat   = _hv[1]
                        _pDict['plane']   = _iPlane
                        _pDict['ordinal'] = _iSat
                        _pDict['host']    = _hk
                        _pruneSatTuple ()

                        self._queue_message (dict (_pDict), 'stop')

                    if len (self.satInts) == 0:
                        self.lastStart = None

            return self._return_text_response (_msg, HTTPStatus.OK)

        def _handle3rdParty ():
            if (_hStatus := _checkPlaneOrdinal ()) != HTTPStatus.OK:
                return self._return_text_response (f'Bad plane/ordinal ({_pDict})', _hStatus)

            _, _msg = _satIntStatus ()

            self._queue_message (_pDict, 'thirdParty')

            return self._return_text_response (_msg, HTTPStatus.OK)

        def _handleInfo ():
            _numSatInts, _msg = _satIntStatus (True)

            _msgs = list ()

            if _numSatInts:
                _intPos = dict ()
                for _iTuples in self.satInts.keys ():
                    _iPlane, _iSat, _interval = _iTuples
                    _poList = _intPos.get (_interval)
                    if _poList is None:
                        _poList = list ()
                        _intPos[_interval] = _poList
                    _poList.append (f'{_iPlane:02d}_{_iSat:02d}')

                for _interval, _poList in _intPos.items ():
                    _msgs.append (f'{_interval}: {sorted (_poList)}')
            
            _msgs.append (_msg)

            return self._return_text_response ('\n'.join (_msgs), HTTPStatus.OK)

        def _getSatIntParams (_pDict: dict):
            if (_iPlane := _pDict.get ('plane')) and (_iSat := _pDict.get ('ordinal')) and \
               (_interval := _pDict.get ('interval')):

                # Validate plane, ordinal, and interval

                if inRangeType  (_iPlane, 1, self._args.num_planes, _openRange = False, _raise = False) and \
                   inRangeType  (_iSat,   1, self._args.num_sats,   _openRange = False, _raise = False) and \
                   minFloatType (_interval, 0.0, False):
                    return _iPlane, _iSat, _interval

            return None

        def _checkPlaneOrdinal ():
            _hStatus = HTTPStatus.OK

            if _iPlane := _pDict.get ('plane'):
                if rangeType (_iPlane, 1, self._args.num_planes, _raise = False):
                    if (_iSat := _pDict.get ('ordinal')) and \
                       not rangeType (_iSat, 1, self._args.num_sats, _raise = False):
                        _hStatus = HTTPStatus.BAD_REQUEST
                else:
                    _hStatus = HTTPStatus.BAD_REQUEST

            return _hStatus

        def _queueStart ():
            if self.lastStart is None:
                self.lastStart = time.time ()

            _d = {'start-time': self.lastStart}

            self._queue_message (_d, 'start')

        if request.method == 'POST':
            _pDict = self._get_post_dict ()

            if   action == 'register':
                if isinstance (_satTuple := _getSatIntParams (_pDict), tuple):
                    self.satInts[_satTuple] = _pDict

                    # When all satellite intervals are registered, publish 'start'

                    if len (self.satInts) == self.totSatInts:
                        _queueStart ()

                    return self._return_text_response ('OK', HTTPStatus.OK)

                return self._return_text_response (f'Bad plane/ordinal ({_pDict})', HTTPStatus.BAD_REQUEST)

            elif action == 'unregister':
                if isinstance (_satTuple := _getSatIntParams (_pDict), tuple):
                    if _satTuple in self.satInts:
                        del self.satInts[_satTuple]
                        if len (self.satInts) == 0:     # no registered sat intervals
                            self.lastStart = None

                        return self._return_text_response ('OK', HTTPStatus.OK)
                    else:
                        return self._return_text_response (f'WARNING: unknown satellite interval ({_pDict})', HTTPStatus.OK)

                return self._return_text_response (f'Bad plane/ordinal ({_pDict})', HTTPStatus.BAD_REQUEST)

            elif action == 'stop':
                return _handleStop ()

            elif action == 'debug':

                # If any satellite intervals are registered, publish 'debug'

                if len (self.satInts):

                    # Validate optional plane and ordinal

                    if (_hStatus := _checkPlaneOrdinal ()) != HTTPStatus.OK:
                        return self._return_text_response (f'Bad plane/ordinal ({_pDict})', _hStatus)

                    # Publish 'debug'

                    self._queue_message (_pDict, 'debug')
                    return self._return_text_response ('OK', HTTPStatus.OK)
                else:
                    return self._return_text_response ('WARNING: no satellite intervals are registered.',
                                                       HTTPStatus.OK)

            elif action == 'exfilt':

                # If any satellite intervals are registered, publish 'exfilt'

                if len (self.satInts):

                    # Validate optional plane and ordinal

                    if (_hStatus := _checkPlaneOrdinal ()) != HTTPStatus.OK:
                        return self._return_text_response (f'Bad plane/ordinal ({_pDict})', _hStatus)

                    # Publish 'exfilt'

                    self._queue_message (_pDict, 'exfilt')
                    return self._return_text_response ('OK', HTTPStatus.OK)
                else:
                    return self._return_text_response ('WARNING: no satellite intervals are registered.',
                                                       HTTPStatus.OK)

            elif action == 'thirdParty':
                return _handle3rdParty ()

        elif request.method == 'GET':
            if   action == 'stop':
                _pdict = dict ()
                return _handleStop ()

            elif action == 'thirdParty':
                _pdict = dict ()
                return _handle3rdParty ()

            elif action == 'info':
                return _handleInfo ()

            elif action == '_start':
                _queueStart ()
            
                return self._return_text_response (f'# sat ints: {len (self.satInts)}', HTTPStatus.OK)

        return self._return_text_response (f'ERROR: unknown "/nodes/" endpoint ("{action}")',
                                           HTTPStatus.BAD_REQUEST)

    # /_eval POST endpoint

    def _eval(self):
        _strIO = StringIO(request.get_data().decode('utf8'))
        return self._return_json_response(self.evalStream(_strIO), HTTPStatus.OK)

    def _teardown(self):
        self._zmq_pub.terminate()
        return self._return_text_response("OK", HTTPStatus.OK)

    # /_shutdown GET endpoint

    def _shutdown(self, _fromSignal=False):
        self._teardown()
        exit()

    ########
    # Main #
    ########

    @override
    def run (self):

        # Start ZeroMQ publication threads

        _, _zmqPubHost, _zmqPubPort = tcpEndpoint (self._args.Q_ZMQ_pub, True)
        _zmqPubHost = '0.0.0.0'
        #print (_zmqPubHost, _zmqPubPort)
        self._zmq_pub = self._ZMQueuePub (_zmqPubHost, 'Q control', _zmqPubPort)

        # Per https://stackoverflow.com/questions/67340101/generating-flask-route-from-class-method
        # because @app.route () decorators don't work for class or instance methods.

        self.flask.route ('/nodes/<action>',     # POST: 'register', 'unregister', 'stop', 'debug', 'exfilt', 'thirdParty'; GET: 'stop', 'thirdParty', 'info', '_start'
                          methods=['POST', 'GET']) (self._nodes_action)
        self.flask.route ('/eval',
                          methods=['POST'])        (self._eval)
        self.flask.route ('/teardown',
                          methods=['GET'])         (self._teardown)
        self.flask.route ('/_shutdown',
                          methods=['GET'])         (self._shutdown)

        _, _restHost, _restPort = httpEndpoint (self._args.Q_endpoint, True)
        _restHost = '0.0.0.0'

        #print (_restHost, _restPort, self._debug)
        self.flask.run (_restHost, _restPort, self._debug,
                        use_reloader = False)        # avoid '* Restarting with stat'

if __name__ == "__main__":
    try:
        FlaskQController ().run ()
    except Exception as _e:
        print (_e)
