#!/usr/bin/env python3

import os
import subprocess
from subprocess import PIPE, DEVNULL#, STDOUT

from IsGood import IsGood

#
# Classes
#

class CLICommand (IsGood):

    _whichCmd = None

    @staticmethod
    def findCommand (_prog, _obj, _attrib, _errMsg = None):
        _cmd = CLICommand (_prog)
        _obj.__setattr__ (_attrib, _cmd if _cmd.isGood else None)
        _obj.appendErrors (_cmd)

    def __init__ (self, _cmd: str, lookUp: bool = True, prefixArgs: tuple = ()):
        super ().__init__ ()

        if lookUp:
            if CLICommand._whichCmd is None:
                CLICommand._whichCmd = CLICommand ('/usr/bin/which', False)

            if not os.path.isfile (_cmd) or not os.access (_cmd, os.X_OK):

                # https://stackoverflow.com/questions/4760215/running-shell-command-and-capturing-the-output

                _result  = CLICommand._whichCmd.run ((_cmd, ), DEVNULL, PIPE, DEVNULL)
                _result.wait ()

                _foundCmd   = _result.stdout.read ().decode ('utf-8').strip ()
                _result.stdout.close ()

                self.isGood = (_foundCmd, f'"{_cmd}" not found')
                _cmd        = _foundCmd

        self._cmd  = _cmd
        self._prfx = prefixArgs

    def run (self, _args: tuple = (), stdin = None, stdout = None, stderr = None):
        _kwargs = {}
        if stdin is not None:
            _kwargs['stdin']  = stdin
        if stdout is not None:
            _kwargs['stdout'] = stdout
        if stderr is not None:
            _kwargs['stderr'] = stderr

        _proc = subprocess.Popen ((*map (lambda _e: str (_e), self._prfx),
                                   self._cmd,
                                   *map (lambda _e: str (_e), _args)),
                                  **_kwargs)

        return _proc

    @property
    def cmd (self):
        return self._cmd
