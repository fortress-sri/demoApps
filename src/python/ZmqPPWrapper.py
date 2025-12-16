#!/usr/bin/env python3

from enum import Enum, auto
import pickle

from zmq.utils import jsonapi


class __AutoName (Enum):
    @staticmethod
    def _generate_next_value_ (name, _start, _count, _last_values):
        return name


class ZmqPPWrapperType (__AutoName):
    def __init__ (self, description):
        self.lower       = self.name.lower ()
        self.description = description

    BYTES = auto (),
    STR   = auto (),
    JSON  = auto (),
    PYOBJ = auto ()

del __AutoName

_ZmqPPEncoders = {
    ZmqPPWrapperType.BYTES: lambda _msg: _msg,
    ZmqPPWrapperType.STR:   lambda _str: _str.encode ('utf-8'),
    ZmqPPWrapperType.JSON:  jsonapi.dumps,
    ZmqPPWrapperType.PYOBJ: lambda _obj: pickle.dumps (_obj, -1)
}

_ZmqPPDecoders = {
    ZmqPPWrapperType.BYTES: lambda _msg: _msg,
    ZmqPPWrapperType.STR:   lambda _msg: _msg.decode ('utf-8'),
    ZmqPPWrapperType.JSON:  jsonapi.loads,
    ZmqPPWrapperType.PYOBJ: pickle.loads
}

def ZmqPPEncoderFor (zmqEncoderType: ZmqPPWrapperType):
    return _ZmqPPEncoders.get (zmqEncoderType)

def ZmqPPDecoderFor (zmqDecoderType: ZmqPPWrapperType):
    return _ZmqPPDecoders.get (zmqDecoderType)
