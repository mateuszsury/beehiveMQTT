"""Tests for beehivemqtt.utils module."""

import pytest
from beehivemqtt.utils import (
    encode_remaining_length,
    decode_remaining_length,
    encode_utf8_string,
    decode_utf8_string,
    validate_topic_name,
    validate_topic_filter,
    generate_client_id
)


class TestRemainingLength:
    """Test MQTT remaining length encoding/decoding."""

    def test_encode_zero(self):
        """Test encoding 0."""
        assert encode_remaining_length(0) == bytearray([0x00])

    def test_encode_127(self):
        """Test encoding 127 (max single byte)."""
        assert encode_remaining_length(127) == bytearray([0x7F])

    def test_encode_128(self):
        """Test encoding 128 (min two bytes)."""
        assert encode_remaining_length(128) == bytearray([0x80, 0x01])

    def test_encode_16383(self):
        """Test encoding 16383 (max two bytes)."""
        assert encode_remaining_length(16383) == bytearray([0xFF, 0x7F])

    def test_encode_16384(self):
        """Test encoding 16384 (min three bytes)."""
        assert encode_remaining_length(16384) == bytearray([0x80, 0x80, 0x01])

    def test_encode_268435455(self):
        """Test encoding 268435455 (max allowed value)."""
        assert encode_remaining_length(268435455) == bytearray([0xFF, 0xFF, 0xFF, 0x7F])

    def test_encode_too_large(self):
        """Test encoding value > max raises ValueError."""
        with pytest.raises(ValueError, match="Remaining length must be 0-268435455"):
            encode_remaining_length(268435456)

    def test_encode_negative(self):
        """Test encoding negative value raises ValueError."""
        with pytest.raises(ValueError, match="Remaining length must be 0-268435455"):
            encode_remaining_length(-1)

    def test_decode_zero(self):
        """Test decoding 0."""
        value, consumed = decode_remaining_length(bytearray([0x00]), 0)
        assert value == 0
        assert consumed == 1

    def test_decode_127(self):
        """Test decoding 127."""
        value, consumed = decode_remaining_length(bytearray([0x7F]), 0)
        assert value == 127
        assert consumed == 1

    def test_decode_128(self):
        """Test decoding 128."""
        value, consumed = decode_remaining_length(bytearray([0x80, 0x01]), 0)
        assert value == 128
        assert consumed == 2

    def test_decode_16383(self):
        """Test decoding 16383."""
        value, consumed = decode_remaining_length(bytearray([0xFF, 0x7F]), 0)
        assert value == 16383
        assert consumed == 2

    def test_decode_16384(self):
        """Test decoding 16384."""
        value, consumed = decode_remaining_length(bytearray([0x80, 0x80, 0x01]), 0)
        assert value == 16384
        assert consumed == 3

    def test_decode_268435455(self):
        """Test decoding max value."""
        value, consumed = decode_remaining_length(bytearray([0xFF, 0xFF, 0xFF, 0x7F]), 0)
        assert value == 268435455
        assert consumed == 4

    def test_decode_with_offset(self):
        """Test decoding with offset."""
        data = bytearray([0xAA, 0xBB, 0x80, 0x01])
        value, consumed = decode_remaining_length(data, offset=2)
        assert value == 128
        assert consumed == 2

    def test_decode_malformed_too_many_bytes(self):
        """Test decoding malformed data (>4 bytes)."""
        with pytest.raises(ValueError, match="Malformed remaining length"):
            decode_remaining_length(bytearray([0x80, 0x80, 0x80, 0x80, 0x80]), 0)

    def test_roundtrip(self):
        """Test encode then decode roundtrip for various values."""
        test_values = [0, 1, 127, 128, 255, 16383, 16384, 65535, 268435455]
        for val in test_values:
            encoded = encode_remaining_length(val)
            decoded, consumed = decode_remaining_length(encoded, 0)
            assert decoded == val, f"Roundtrip failed for {val}"
            assert consumed == len(encoded)


class TestUTF8String:
    """Test MQTT UTF-8 string encoding/decoding."""

    def test_encode_ascii(self):
        """Test encoding ASCII string."""
        result = encode_utf8_string("hello")
        assert result == bytearray([0x00, 0x05]) + b'hello'

    def test_encode_unicode(self):
        """Test encoding Unicode string."""
        result = encode_utf8_string("café")
        expected = bytearray([0x00, 0x05]) + "café".encode('utf-8')
        assert result == expected

    def test_encode_empty(self):
        """Test encoding empty string."""
        result = encode_utf8_string("")
        assert result == bytearray([0x00, 0x00])

    def test_encode_bytes(self):
        """Test encoding bytes directly."""
        result = encode_utf8_string(b"test")
        assert result == bytearray([0x00, 0x04]) + b'test'

    def test_decode_ascii(self):
        """Test decoding ASCII string."""
        data = bytearray([0x00, 0x05]) + b'hello'
        string, offset = decode_utf8_string(data, 0)
        assert string == b'hello'
        assert offset == 7

    def test_decode_unicode(self):
        """Test decoding Unicode string."""
        data = bytearray([0x00, 0x05]) + "café".encode('utf-8')
        string, offset = decode_utf8_string(data, 0)
        assert string == "café".encode('utf-8')

    def test_decode_empty(self):
        """Test decoding empty string."""
        data = bytearray([0x00, 0x00])
        string, offset = decode_utf8_string(data, 0)
        assert string == b''
        assert offset == 2

    def test_decode_with_offset(self):
        """Test decoding with offset."""
        data = bytearray([0xFF, 0xFF, 0x00, 0x03]) + b'foo'
        string, offset = decode_utf8_string(data, 2)
        assert string == b'foo'
        assert offset == 7

    def test_roundtrip_ascii(self):
        """Test encode/decode roundtrip with ASCII."""
        original = "test string"
        encoded = encode_utf8_string(original)
        decoded, offset = decode_utf8_string(encoded, 0)
        assert decoded.decode('utf-8') == original

    def test_roundtrip_unicode(self):
        """Test encode/decode roundtrip with Unicode."""
        original = "Hello 世界 🌍"
        encoded = encode_utf8_string(original)
        decoded, offset = decode_utf8_string(encoded, 0)
        assert decoded.decode('utf-8') == original


class TestValidateTopicName:
    """Test MQTT topic name validation (for PUBLISH)."""

    def test_valid_simple_topic(self):
        """Test valid simple topic."""
        assert validate_topic_name("home/temperature") is True

    def test_valid_single_level(self):
        """Test valid single level topic."""
        assert validate_topic_name("temp") is True

    def test_valid_deep_topic(self):
        """Test valid deep topic hierarchy."""
        assert validate_topic_name("a/b/c/d/e/f") is True

    def test_valid_bytes(self):
        """Test valid topic as bytes."""
        assert validate_topic_name(b"test/topic") is True

    def test_empty_topic(self):
        """Test empty topic raises ValueError."""
        with pytest.raises(ValueError, match="Topic name cannot be empty"):
            validate_topic_name("")

    def test_empty_bytes(self):
        """Test empty bytes topic raises ValueError."""
        with pytest.raises(ValueError, match="Topic name cannot be empty"):
            validate_topic_name(b"")

    def test_too_long_topic(self):
        """Test topic exceeding max length raises ValueError."""
        long_topic = "a" * 257
        with pytest.raises(ValueError, match="Topic name exceeds maximum length"):
            validate_topic_name(long_topic)

    def test_wildcard_plus(self):
        """Test topic with + wildcard raises ValueError."""
        with pytest.raises(ValueError, match="Topic name cannot contain wildcards"):
            validate_topic_name("home/+/temperature")

    def test_wildcard_hash(self):
        """Test topic with # wildcard raises ValueError."""
        with pytest.raises(ValueError, match="Topic name cannot contain wildcards"):
            validate_topic_name("home/#")

    def test_custom_max_length(self):
        """Test custom max length parameter."""
        assert validate_topic_name("ab", max_length=2) is True
        with pytest.raises(ValueError, match="exceeds maximum length"):
            validate_topic_name("abc", max_length=2)


class TestValidateTopicFilter:
    """Test MQTT topic filter validation (for SUBSCRIBE)."""

    def test_valid_simple_filter(self):
        """Test valid simple topic filter."""
        assert validate_topic_filter("home/temperature") is True

    def test_valid_plus_wildcard(self):
        """Test valid + wildcard."""
        assert validate_topic_filter("home/+/temperature") is True

    def test_valid_hash_wildcard(self):
        """Test valid # wildcard at end."""
        assert validate_topic_filter("home/#") is True

    def test_valid_hash_only(self):
        """Test # wildcard alone."""
        assert validate_topic_filter("#") is True

    def test_valid_plus_only(self):
        """Test + wildcard alone."""
        assert validate_topic_filter("+") is True

    def test_valid_multiple_plus(self):
        """Test multiple + wildcards."""
        assert validate_topic_filter("+/+/+") is True

    def test_valid_bytes(self):
        """Test valid filter as bytes."""
        assert validate_topic_filter(b"home/+") is True

    def test_empty_filter(self):
        """Test empty filter raises ValueError."""
        with pytest.raises(ValueError, match="Topic filter cannot be empty"):
            validate_topic_filter("")

    def test_too_long_filter(self):
        """Test filter exceeding max length raises ValueError."""
        long_filter = "a" * 257
        with pytest.raises(ValueError, match="Topic filter exceeds maximum length"):
            validate_topic_filter(long_filter)

    def test_hash_not_at_end(self):
        """Test # wildcard not at end raises ValueError."""
        with pytest.raises(ValueError, match="# wildcard must be last character"):
            validate_topic_filter("home/#/temperature")

    def test_hash_not_after_slash(self):
        """Test # wildcard not alone or after / raises ValueError."""
        with pytest.raises(ValueError, match="# must be alone or after /"):
            validate_topic_filter("home#")

    def test_plus_not_occupying_full_level(self):
        """Test + wildcard not occupying full level raises ValueError."""
        with pytest.raises(ValueError, match=r"\+ must occupy entire level"):
            validate_topic_filter("home/te+st")

    def test_plus_with_text_at_start(self):
        """Test + wildcard with text at level start raises ValueError."""
        with pytest.raises(ValueError, match=r"\+ must occupy entire level"):
            validate_topic_filter("home/+test")

    def test_plus_with_text_at_end(self):
        """Test + wildcard with text at level end raises ValueError."""
        with pytest.raises(ValueError, match=r"\+ must occupy entire level"):
            validate_topic_filter("home/test+")


class TestGenerateClientId:
    """Test client ID generation."""

    def test_generate_format(self):
        """Test generated client ID has correct format."""
        client_id = generate_client_id()
        assert client_id.startswith("beehive-")
        assert len(client_id) == 16  # "beehive-" + 8 hex chars

    def test_generate_unique(self):
        """Test generated IDs are reasonably unique."""
        ids = set()
        for _ in range(100):
            client_id = generate_client_id()
            ids.add(client_id)
        # Should have at least some unique values (time-based, so might collide if very fast)
        assert len(ids) > 1

    def test_generate_hex_chars(self):
        """Test generated ID contains only hex characters after prefix."""
        client_id = generate_client_id()
        hex_part = client_id[8:]  # Skip "beehive-"
        assert all(c in '0123456789abcdef' for c in hex_part)
