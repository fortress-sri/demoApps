class IsGood (object):

    def __init__ (self):
        object.__init__ (self)
        self.resetIsGood ()

    @property
    def isGood (self):
        return self._isGood

    @isGood.setter
    def isGood (self, _obj):
        if isinstance (_obj, tuple):
            _new = _obj[0]
            _msg = _obj[1]
        else:
            _new = _obj
            _msg = None

        if not _new:
            self._isGood = False
            if _msg:
                self._err_msgs.append (_msg)

    @property
    def errorMessages (self):
        return '\n'.join (self._err_msgs)

    @property
    def rawErrorMessages (self):
        return self._err_msgs

    def appendErrors (self, _obj):
        if   isinstance (_obj, type (self)):
            self._isGood   &= _obj.isGood
            self._err_msgs += _obj._err_msgs

        elif isinstance (_obj, list):
            self._isGood   &= len (_obj) == 0
            self._err_msgs += _obj

        else:
            self._isGood = False
            self._err_msgs.append (_obj)

    def resetIsGood (self):
        self._isGood   = True
        self._err_msgs = []
