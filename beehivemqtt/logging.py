"""Lightweight logging for BeehiveMQTT."""

DEBUG = 0
INFO = 1
WARNING = 2
ERROR = 3

_LEVEL_NAMES = {0: 'DEBUG', 1: 'INFO', 2: 'WARN', 3: 'ERROR'}
_NAME_LEVELS = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3}

class Logger:
    __slots__ = ('name', 'level')

    def __init__(self, name, level=INFO):
        self.name = name
        if isinstance(level, str):
            self.level = _NAME_LEVELS.get(level, INFO)
        else:
            self.level = level

    def _log(self, level, msg, *args):
        if level >= self.level:
            if args:
                msg = msg % args
            print("[%s] %s: %s" % (_LEVEL_NAMES.get(level, '?'), self.name, msg))

    def debug(self, msg, *args):
        self._log(DEBUG, msg, *args)

    def info(self, msg, *args):
        self._log(INFO, msg, *args)

    def warning(self, msg, *args):
        self._log(WARNING, msg, *args)

    def error(self, msg, *args):
        self._log(ERROR, msg, *args)

_loggers = {}

def get_logger(name, level=INFO):
    if name not in _loggers:
        _loggers[name] = Logger(name, level)
    return _loggers[name]
