"""
BeehiveMQTT Exception Hierarchy

Custom exceptions for MQTT 3.1.1 broker protocol violations,
authentication failures, connection errors, and payload issues.
MicroPython-optimized with __slots__ for minimal RAM usage.
"""


class MQTTError(Exception):
    """Base exception for all MQTT-related errors."""
    __slots__ = ('message',)

    def __init__(self, message):
        self.message = message
        super().__init__(message)


class MQTTProtocolError(MQTTError):
    """Protocol violation error with optional MQTT reason code."""
    __slots__ = ('reason_code',)

    def __init__(self, message, reason_code=None):
        super().__init__(message)
        self.reason_code = reason_code


class MQTTAuthError(MQTTError):
    """Authentication or authorization failure."""
    __slots__ = ()

    def __init__(self, message):
        super().__init__(message)


class MQTTConnectionError(MQTTError):
    """Connection-level error (network, timeout, disconnect)."""
    __slots__ = ()

    def __init__(self, message):
        super().__init__(message)


class MQTTPayloadError(MQTTError):
    """Payload too large, malformed, or invalid data."""
    __slots__ = ()

    def __init__(self, message):
        super().__init__(message)
