#!/usr/bin/env python3

import argparse
from   datetime import datetime, timezone
from   http import HTTPStatus
from   io import StringIO
import json
import logging          # .getLogger (), .Formatter (), .FileHandler ()
import os               # .path .environ
import requests
import signal
import subprocess       # .run ()
import sys
import time
from   typing import override

from   flask import Flask, abort, request

# CLI arg parsing and server invocation

from   jsonArgParse import JSONArgParse

###########
# Globals #
###########

_main_path = os.path.abspath(str(sys.modules['__main__'].__file__))
_base_path = os.path.basename(_main_path)
_base_name, _ = os.path.splitext(_base_path)

_logger  = logging.getLogger(_base_name)
_started = time.time()

del _, _main_path, _base_path


class WebHook (JSONArgParse):

    # https://stackoverflow.com/questions/5160077/encoding-nested-python-object-in-json

    class _AsJSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if hasattr(obj, 'asJSON'):
                return obj.asJSON()
            else:
                return json.JSONEncoder.default(self, obj)

    class _ConfigData:
        def __init__(self):
            self.config_path		= None
            self.config_data		= None
            self.HIL_nodes		= None
            self.remove_service_cmd	= None
            self.kill_container_cmd	= None
            self.remote_user		= None
            self.suppression_limit	= None

        def get (self, key, default_value=None):
            if self.config_path is None:
                self.config_path = os.environ.get('JSON_CONF_PATH', '')
                if self.config_path:
                    try:
                        with open (self.config_path) as config_file:
                            self.config_data = json.load (config_file)
                        _logger.debug (f'JSON_CONF_PATH="{self.config_path}" loaded: {self.config_data.__class__}')
                        _logger.debug (f'Config data has {len(self.config_data)} elements')
                    except Exception as e:
                        _logger.debug (f'JSON_CONF_PATH="{self.config_path}" load failed: {e}')
                else:
                    _logger.debug (f'JSON_CONF_PATH="{self.config_path}" not loaded.')
            if isinstance (self.config_data, dict):
                return self.config_data.get (key, default_value)
            return default_value

        def isHILnode (self, node_name):
            if not self.HIL_nodes:
                self.HIL_nodes = self.get ("HIL")
            if isinstance (self.HIL_nodes, dict):
                return node_name in self.HIL_nodes
            # If no config file, assume all nodes are HIL nodes
            return True

        def get_kill_container_command(self):
            if not self.kill_container_cmd:
                self.kill_container_cmd = self.get ('WebHook-kill_container_command')
            if not self.kill_container_cmd:
                self.kill_container_cmd = os.environ.get('KILL_CONTAINER_CMD', 'docker kill ${ContainerID}')
            return self.kill_container_cmd

        def get_remove_service_command(self):
            if not self.remove_service_cmd:
                self.remove_service_cmd = self.get ('WebHook-remove_service_command')
            if not self.remove_service_cmd:
                self.remove_service_cmd = os.environ.get('REMOVE_SERVICE_CMD', 'fortress_admin/OpenHorizon/kill_edge_node_thirdpartyapp.bash')
            return self.remove_service_cmd

        def get_remote_user(self):
            if not self.remote_user:
                self.remote_user = self.get ('WebHook-remote_user')
            if not self.remote_user:
                self.remote_user = os.environ.get('REMOTE_USER', os.environ.get('USER', 'fortress'))
            return self.remote_user

    class _EnventTracking:
        def __init__(self, config_data):
            self.config_data	= config_data
            self.hosts		= { }

        def suppression_check (self, _host, _event_ts, _action):
            if _event_ts < _started:
                return f' prior to start: {_started}'
            host_data	= self.hosts.setdefault (_host, {})
            event_data	= host_data.setdefault (_action, {})
            _last_ts	= event_data.get ('last_ts')
            if _last_ts:
                if _last_ts > _event_ts:
                    return f' prior to last: {_last_ts}'
                _delta_ts = _event_ts - _last_ts
                _suppression_limit = self.config_data.get ('WebHook-suppression_limit', 120)
                if _delta_ts < _suppression_limit:
                    return f' delta {_delta_ts} within {_suppression_limit} seconds of last'
            event_data['last_ts'] = _event_ts
            return ''

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

        self.flask  = Flask (__name__)
        self._debug = self._args.debug

        self._polCB = {"satapp-unauthorized-execution":	self._log_alert,
                       "satapp-unauthorized-net-audit":	self._remove_service,
                       "satapp-block-file-writes":	self._kill_container
                      }

        self.config_data = self._ConfigData()
        self.tracking	 = self._EnventTracking (self.config_data)

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

    def _return_image_response (self, _obj, _status, _iType):
        return self._return_response(_obj, _status, lambda _cnt: _cnt, f'image/{_iType}')

    def _key_value_substitutions (self, _cmd_string, _event_json, _key_prefix=""):
        for (_key,_value) in _event_json.items():
            if isinstance (_value, dict):
                _cmd_string = self._key_value_substitutions (_cmd_string, _value, f'{_key_prefix}{_key}.')
            else:
                _cmd_string = _cmd_string.replace (f'${{{_key_prefix}{_key}}}', f'"{_value}"')
            continue
        return _cmd_string

    def _execute_remote_command (self, _remote_cmd, _action, _host, _event_json, _top_json):
        _is_test_alert	= _event_json is _top_json
        _remote_user 	= self.config_data.get_remote_user()
        _event_ts	= _event_json.get('Timestamp')
        _run_command	= _remote_cmd and _remote_user and _event_ts and _host and self.config_data.isHILnode (_host)
        _add_text	= ''
        if _run_command and not _is_test_alert:
            _add_text    = self.tracking.suppression_check (_host, _event_ts, _action)
            _run_command = not _add_text
        if _run_command:
            _remote_cmd = self._key_value_substitutions (_remote_cmd, _event_json)
            if _event_json is not _top_json:
                _remote_cmd = self._key_value_substitutions (_remote_cmd, _top_json)
        _logger.debug (f'{_action}: {_event_json.get ("PolicyName")}, {_host} user={_remote_user} cmd={_remote_cmd} is_test={_is_test_alert} run={_run_command} ts={_event_ts}{_add_text}')
        if _run_command:
            _to_run=f'ssh {_remote_user}@{_host} {_remote_cmd}'
            try:
                _result = subprocess.run (_to_run, shell=True, capture_output=True, text=True, check=True)
                _logger.debug (f'Command "{_to_run}" completed')
                if _result.stdout:
                    _logger.debug (f'stdout:\n{_result.stdout.strip()}')
                if _result.stderr:
                    _logger.debug (f'stderr:\n{_result.stderr.strip()}')
            except subprocess.CalledProcessError as e:
                _logger.debug (f'Command "{_to_run}" failed {e}')
                if e.stdout:
                    _logger.debug (f'stdout:\n{e.stdout}')
                if e.stderr:
                    _logger.debug (f'stderr:\n{e.stderr}')
            except Exception as e:
                _logger.debug (f'Command "{_to_run}" failed: {e}')

    ####################
    # Policy callbacks #
    ####################

    def _log_alert (self, _host: str, _event_json: dict, _top_json: dict):
        _logger.debug (f'{_event_json.get ("PolicyName")}, {_host} {_event_json.get("Timestamp")}')

    def _kill_container (self, _host: str, _event_json: dict, _top_json: dict):     # causes rollback
        _remote_cmd	= self.config_data.get_kill_container_command()
        self._execute_remote_command (_remote_cmd, "kill_container", _host, _event_json, _top_json)

    def _remove_service (self, _host: str, _event_json: dict, _top_json: dict):     # disable 3rd party app
        _remote_cmd	= self.config_data.get_remove_service_command()
        self._execute_remote_command (_remote_cmd, "remove_service", _host, _event_json, _top_json)

    #############
    # Endpoints #
    #############

    # /api/webHook POST endpoint

    def _webhook (self):

        if (request.method == 'POST') and (_pTopDict := self._get_post_dict ()):
            _pDict  = _pTopDict
            _pEvent = _pTopDict
            if (_pPayload  := _pTopDict.get ("client_payload")) and \
               (_pEventTmp := _pPayload.get ("event")):
                _pEvent = _pEventTmp
            if (_eHost := _pEvent.get ("HostName")) and \
               (_polCB := self._polCB.get (_pEvent.get ("PolicyName"))):
                _polCB (_eHost, _pEvent, _pDict)
                return self._return_text_response ("OK", HTTPStatus.OK)
            else:
                _logger.debug (f'Payload issue:\n{json.dumps(_pDict,indent=2)}')

        return self._return_text_response (f'ERROR: bad "/api/webHook" request',
                                           HTTPStatus.BAD_REQUEST)

    # /_eval POST endpoint

    def _eval(self):
        _strIO = StringIO(request.get_data().decode('utf8'))
        return self._return_json_response(self.evalStream(_strIO), HTTPStatus.OK)

    def _shutdown(self, _fromSignal=False):
        if _func := request.environ.get('werkzeug.server.shutdown'):
            _func()
        else:
            raise RuntimeError('Not running with the Werkzeug Server')

        return self._return_text_response("OK", HTTPStatus.OK)

    ########
    # Main #
    ########

    def run (self):
        # Per https://stackoverflow.com/questions/67340101/generating-flask-route-from-class-method
        # because @app.route () decorators don't work for class or instance methods.

        self.flask.route ('/api/webHook',   # POST
                          methods=['POST']) (self._webhook)
        self.flask.route ('/eval',
                          methods=['POST']) (self._eval)
        self.flask.route ('/_shutdown',
                          methods=['GET'])  (self._shutdown)

        # Process HOST and PORT environment variables
        _host = os.getenv ('HOST', '127.0.0.1')
        _port = os.getenv ('PORT', 5000)
        if _port:
            _port = int (_port)

        #print (_host, _port, self._debug)
        self.flask.run (_host, _port, self._debug,
                        use_reloader = False)        # avoid '* Restarting with stat'

if __name__ == "__main__":
    try:
        WebHook ().run ()
    except Exception as _e:
        print (_e)
