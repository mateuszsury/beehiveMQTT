"""Tests for beehivemqtt.config module."""

import pytest
from beehivemqtt.config import BrokerConfig


class TestBrokerConfigDefaults:
    """Test default configuration values."""

    def test_default_values(self):
        """Check all default values are correct."""
        cfg = BrokerConfig()

        # Network settings
        assert cfg.bind_addr == '0.0.0.0'
        assert cfg.port == 1883
        assert cfg.backlog == 4

        # Client limits
        assert cfg.max_clients == 10
        assert cfg.max_subscriptions_per_client == 20
        assert cfg.max_topic_length == 256
        assert cfg.max_topic_levels == 8

        # Message size limits
        assert cfg.max_payload_size == 4096
        assert cfg.max_packet_size == 8192
        assert cfg.max_queued_messages == 50

        # QoS settings
        assert cfg.max_inflight == 10
        assert cfg.max_retained_messages == 100

        # Timeout and keep-alive
        assert cfg.connect_timeout == 10
        assert cfg.keep_alive_factor == 1.5
        assert cfg.no_keepalive_timeout == 3600

        # QoS retry settings
        assert cfg.qos_retry_interval == 10
        assert cfg.qos_max_retries == 3

        # Session management
        assert cfg.session_expiry == 3600

        # Feature flags
        assert cfg.allow_anonymous is True
        assert cfg.allow_zero_length_clientid is True
        assert cfg.retain_enabled is True
        assert cfg.qos2_enabled is True

        # System topics and stats
        assert cfg.sys_topics_enabled is True
        assert cfg.stats_interval == 60

        # Memory and performance
        assert cfg.recv_buffer_size == 1024
        assert cfg.gc_collect_interval == 30

        # Logging
        assert cfg.log_level == 'INFO'

    def test_kwargs_override(self):
        """Verify kwargs override default values."""
        cfg = BrokerConfig(
            port=8883,
            max_clients=50,
            log_level='DEBUG',
            bind_addr='127.0.0.1',
            keep_alive_factor=2.0,
            allow_anonymous=False,
        )
        assert cfg.port == 8883
        assert cfg.max_clients == 50
        assert cfg.log_level == 'DEBUG'
        assert cfg.bind_addr == '127.0.0.1'
        assert cfg.keep_alive_factor == 2.0
        assert cfg.allow_anonymous is False

        # Non-overridden values should stay at defaults
        assert cfg.backlog == 4
        assert cfg.max_payload_size == 4096
        assert cfg.session_expiry == 3600

    def test_new_fields_exist(self):
        """Verify max_topic_levels and no_keepalive_timeout fields exist."""
        cfg = BrokerConfig()
        assert hasattr(cfg, 'max_topic_levels')
        assert hasattr(cfg, 'no_keepalive_timeout')
        assert cfg.max_topic_levels == 8
        assert cfg.no_keepalive_timeout == 3600


class TestBrokerConfigValidation:
    """Test validate() method catches invalid parameters."""

    def test_valid_config_passes(self):
        """Default config should pass validation without errors."""
        cfg = BrokerConfig()
        cfg.validate()  # Should not raise

    def test_validate_port_range_too_low(self):
        """Port below 1 should raise ValueError."""
        cfg = BrokerConfig(port=0)
        with pytest.raises(ValueError, match='port must be in range 1-65535'):
            cfg.validate()

    def test_validate_port_range_too_high(self):
        """Port above 65535 should raise ValueError."""
        cfg = BrokerConfig(port=70000)
        with pytest.raises(ValueError, match='port must be in range 1-65535'):
            cfg.validate()

    def test_validate_port_range_boundaries(self):
        """Port at boundary values 1 and 65535 should pass validation."""
        cfg_low = BrokerConfig(port=1)
        cfg_low.validate()

        cfg_high = BrokerConfig(port=65535)
        cfg_high.validate()

    def test_validate_max_clients(self):
        """max_clients must be >= 1."""
        cfg = BrokerConfig(max_clients=0)
        with pytest.raises(ValueError, match='max_clients must be >= 1'):
            cfg.validate()

    def test_validate_max_payload_size(self):
        """max_payload_size must be >= 1."""
        cfg = BrokerConfig(max_payload_size=0, max_packet_size=8192)
        with pytest.raises(ValueError, match='max_payload_size must be >= 1'):
            cfg.validate()

    def test_validate_backlog(self):
        """backlog must be >= 1."""
        cfg = BrokerConfig(backlog=0)
        with pytest.raises(ValueError, match='backlog must be >= 1'):
            cfg.validate()

    def test_validate_max_subscriptions(self):
        """max_subscriptions_per_client must be >= 1."""
        cfg = BrokerConfig(max_subscriptions_per_client=0)
        with pytest.raises(ValueError, match='max_subscriptions_per_client must be >= 1'):
            cfg.validate()

    def test_validate_max_topic_length_too_low(self):
        """max_topic_length below 1 should raise ValueError."""
        cfg = BrokerConfig(max_topic_length=0)
        with pytest.raises(ValueError, match='max_topic_length must be in range 1-65535'):
            cfg.validate()

    def test_validate_max_topic_length_too_high(self):
        """max_topic_length above 65535 should raise ValueError."""
        cfg = BrokerConfig(max_topic_length=65536)
        with pytest.raises(ValueError, match='max_topic_length must be in range 1-65535'):
            cfg.validate()

    def test_validate_max_topic_levels(self):
        """max_topic_levels must be >= 1."""
        cfg = BrokerConfig(max_topic_levels=0)
        with pytest.raises(ValueError, match='max_topic_levels must be >= 1'):
            cfg.validate()

    def test_validate_max_packet_size_vs_payload(self):
        """max_packet_size must be >= max_payload_size."""
        cfg = BrokerConfig(max_payload_size=4096, max_packet_size=2048)
        with pytest.raises(ValueError, match='max_packet_size must be >= max_payload_size'):
            cfg.validate()

    def test_validate_max_packet_size_equal_to_payload(self):
        """max_packet_size equal to max_payload_size should pass."""
        cfg = BrokerConfig(max_payload_size=4096, max_packet_size=4096)
        cfg.validate()  # Should not raise

    def test_validate_max_queued_messages(self):
        """max_queued_messages must be >= 0."""
        cfg = BrokerConfig(max_queued_messages=-1)
        with pytest.raises(ValueError, match='max_queued_messages must be >= 0'):
            cfg.validate()

    def test_validate_max_queued_messages_zero_allowed(self):
        """max_queued_messages of 0 should pass validation."""
        cfg = BrokerConfig(max_queued_messages=0)
        cfg.validate()  # Should not raise

    def test_validate_max_inflight(self):
        """max_inflight must be >= 1."""
        cfg = BrokerConfig(max_inflight=0)
        with pytest.raises(ValueError, match='max_inflight must be >= 1'):
            cfg.validate()

    def test_validate_max_retained_messages(self):
        """max_retained_messages must be >= 0."""
        cfg = BrokerConfig(max_retained_messages=-1)
        with pytest.raises(ValueError, match='max_retained_messages must be >= 0'):
            cfg.validate()

    def test_validate_max_retained_messages_zero_allowed(self):
        """max_retained_messages of 0 should pass validation."""
        cfg = BrokerConfig(max_retained_messages=0)
        cfg.validate()  # Should not raise

    def test_validate_connect_timeout(self):
        """connect_timeout must be >= 1."""
        cfg = BrokerConfig(connect_timeout=0)
        with pytest.raises(ValueError, match='connect_timeout must be >= 1'):
            cfg.validate()

    def test_validate_keep_alive_factor(self):
        """keep_alive_factor must be > 0."""
        cfg = BrokerConfig(keep_alive_factor=0)
        with pytest.raises(ValueError, match='keep_alive_factor must be > 0'):
            cfg.validate()

    def test_validate_keep_alive_factor_negative(self):
        """Negative keep_alive_factor should raise ValueError."""
        cfg = BrokerConfig(keep_alive_factor=-1.0)
        with pytest.raises(ValueError, match='keep_alive_factor must be > 0'):
            cfg.validate()

    def test_validate_no_keepalive_timeout(self):
        """no_keepalive_timeout must be >= 1."""
        cfg = BrokerConfig(no_keepalive_timeout=0)
        with pytest.raises(ValueError, match='no_keepalive_timeout must be >= 1'):
            cfg.validate()

    def test_validate_qos_retry_interval(self):
        """qos_retry_interval must be >= 1."""
        cfg = BrokerConfig(qos_retry_interval=0)
        with pytest.raises(ValueError, match='qos_retry_interval must be >= 1'):
            cfg.validate()

    def test_validate_qos_max_retries(self):
        """qos_max_retries must be >= 0."""
        cfg = BrokerConfig(qos_max_retries=-1)
        with pytest.raises(ValueError, match='qos_max_retries must be >= 0'):
            cfg.validate()

    def test_validate_qos_max_retries_zero_allowed(self):
        """qos_max_retries of 0 should pass validation."""
        cfg = BrokerConfig(qos_max_retries=0)
        cfg.validate()  # Should not raise

    def test_validate_session_expiry(self):
        """session_expiry must be >= 0."""
        cfg = BrokerConfig(session_expiry=-1)
        with pytest.raises(ValueError, match='session_expiry must be >= 0'):
            cfg.validate()

    def test_validate_session_expiry_zero_allowed(self):
        """session_expiry of 0 should pass validation."""
        cfg = BrokerConfig(session_expiry=0)
        cfg.validate()  # Should not raise

    def test_validate_stats_interval(self):
        """stats_interval must be >= 1."""
        cfg = BrokerConfig(stats_interval=0)
        with pytest.raises(ValueError, match='stats_interval must be >= 1'):
            cfg.validate()

    def test_validate_recv_buffer_size(self):
        """recv_buffer_size must be >= 64."""
        cfg = BrokerConfig(recv_buffer_size=63)
        with pytest.raises(ValueError, match='recv_buffer_size must be >= 64'):
            cfg.validate()

    def test_validate_recv_buffer_size_boundary(self):
        """recv_buffer_size of exactly 64 should pass validation."""
        cfg = BrokerConfig(recv_buffer_size=64)
        cfg.validate()  # Should not raise

    def test_validate_gc_collect_interval(self):
        """gc_collect_interval must be >= 1."""
        cfg = BrokerConfig(gc_collect_interval=0)
        with pytest.raises(ValueError, match='gc_collect_interval must be >= 1'):
            cfg.validate()

    def test_validate_log_level_invalid(self):
        """Invalid log_level should raise ValueError."""
        cfg = BrokerConfig(log_level='TRACE')
        with pytest.raises(ValueError, match='log_level must be one of'):
            cfg.validate()

    def test_validate_log_level_valid_values(self):
        """All valid log levels should pass validation."""
        for level in ('DEBUG', 'INFO', 'WARNING', 'ERROR'):
            cfg = BrokerConfig(log_level=level)
            cfg.validate()  # Should not raise
