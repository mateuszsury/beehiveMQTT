"""Tests for beehivemqtt.errors exception hierarchy."""

import pytest
from beehivemqtt.errors import (
    MQTTError,
    MQTTProtocolError,
    MQTTAuthError,
    MQTTConnectionError,
    MQTTPayloadError
)


class TestMQTTError:
    """Test base MQTTError class."""

    def test_message_attribute(self):
        """Test MQTTError stores message."""
        e = MQTTError("test message")
        assert e.message == "test message"

    def test_str_representation(self):
        """Test MQTTError string representation."""
        e = MQTTError("something failed")
        assert "something failed" in str(e)

    def test_is_exception(self):
        """Test MQTTError is an Exception."""
        assert issubclass(MQTTError, Exception)

    def test_has_slots(self):
        """Test MQTTError uses __slots__."""
        assert hasattr(MQTTError, '__slots__')
        assert 'message' in MQTTError.__slots__


class TestMQTTProtocolError:
    """Test MQTTProtocolError class."""

    def test_inherits_mqtt_error(self):
        """Test MQTTProtocolError is subclass of MQTTError."""
        assert issubclass(MQTTProtocolError, MQTTError)

    def test_isinstance_check(self):
        """Test isinstance works for hierarchy."""
        e = MQTTProtocolError("protocol violation")
        assert isinstance(e, MQTTError)
        assert isinstance(e, MQTTProtocolError)
        assert isinstance(e, Exception)

    def test_reason_code_default_none(self):
        """Test reason_code defaults to None."""
        e = MQTTProtocolError("test")
        assert e.reason_code is None

    def test_reason_code_set(self):
        """Test reason_code can be set."""
        e = MQTTProtocolError("bad packet", reason_code=0x01)
        assert e.reason_code == 0x01
        assert e.message == "bad packet"

    def test_has_slots(self):
        """Test __slots__ includes reason_code."""
        assert 'reason_code' in MQTTProtocolError.__slots__


class TestMQTTAuthError:
    """Test MQTTAuthError class."""

    def test_inherits_mqtt_error(self):
        """Test MQTTAuthError is subclass of MQTTError."""
        assert issubclass(MQTTAuthError, MQTTError)

    def test_isinstance_check(self):
        """Test isinstance for auth error."""
        e = MQTTAuthError("not authorized")
        assert isinstance(e, MQTTError)
        assert isinstance(e, MQTTAuthError)
        assert not isinstance(e, MQTTProtocolError)

    def test_message_stored(self):
        """Test message is accessible."""
        e = MQTTAuthError("access denied")
        assert e.message == "access denied"


class TestMQTTConnectionError:
    """Test MQTTConnectionError class."""

    def test_inherits_mqtt_error(self):
        """Test inheritance."""
        assert issubclass(MQTTConnectionError, MQTTError)

    def test_isinstance_check(self):
        """Test isinstance."""
        e = MQTTConnectionError("connection lost")
        assert isinstance(e, MQTTError)
        assert isinstance(e, MQTTConnectionError)
        assert not isinstance(e, MQTTAuthError)


class TestMQTTPayloadError:
    """Test MQTTPayloadError class."""

    def test_inherits_mqtt_error(self):
        """Test inheritance."""
        assert issubclass(MQTTPayloadError, MQTTError)

    def test_isinstance_check(self):
        """Test isinstance."""
        e = MQTTPayloadError("payload too large")
        assert isinstance(e, MQTTError)
        assert isinstance(e, MQTTPayloadError)

    def test_message_stored(self):
        """Test message."""
        e = MQTTPayloadError("too big")
        assert e.message == "too big"


class TestExceptionHierarchy:
    """Test the full exception hierarchy."""

    def test_all_are_mqtt_errors(self):
        """Test all custom exceptions inherit from MQTTError."""
        for cls in [MQTTProtocolError, MQTTAuthError, MQTTConnectionError, MQTTPayloadError]:
            e = cls("test")
            assert isinstance(e, MQTTError)

    def test_siblings_not_related(self):
        """Test sibling exceptions are not instances of each other."""
        proto = MQTTProtocolError("a")
        auth = MQTTAuthError("b")
        conn = MQTTConnectionError("c")
        payload = MQTTPayloadError("d")

        assert not isinstance(proto, MQTTAuthError)
        assert not isinstance(auth, MQTTConnectionError)
        assert not isinstance(conn, MQTTPayloadError)
        assert not isinstance(payload, MQTTProtocolError)

    def test_catch_by_base_class(self):
        """Test catching by MQTTError catches all subtypes."""
        caught = []
        for cls in [MQTTProtocolError, MQTTAuthError, MQTTConnectionError, MQTTPayloadError]:
            try:
                raise cls("test %s" % cls.__name__)
            except MQTTError as e:
                caught.append(e.message)

        assert len(caught) == 4
