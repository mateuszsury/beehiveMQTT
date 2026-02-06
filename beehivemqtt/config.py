"""
BeehiveMQTT Broker Configuration

MicroPython-compatible configuration class for MQTT 3.1.1 broker.
Uses __slots__ for minimal memory footprint.
"""


class BrokerConfig:
    """Configuration parameters for BeehiveMQTT broker."""

    __slots__ = (
        'bind_addr', 'port', 'backlog',
        'max_clients', 'max_subscriptions_per_client', 'max_topic_length',
        'max_topic_levels',
        'max_payload_size', 'max_packet_size', 'max_queued_messages',
        'max_inflight', 'max_retained_messages',
        'connect_timeout', 'keep_alive_factor', 'no_keepalive_timeout',
        'qos_retry_interval', 'qos_max_retries',
        'session_expiry',
        'allow_anonymous', 'allow_zero_length_clientid',
        'retain_enabled', 'qos2_enabled',
        'sys_topics_enabled', 'stats_interval',
        'recv_buffer_size', 'gc_collect_interval',
        'log_level'
    )

    def __init__(self, **kwargs):
        """Initialize broker configuration with defaults, override with kwargs."""
        # Network settings
        self.bind_addr = '0.0.0.0'
        self.port = 1883
        self.backlog = 4

        # Client limits
        self.max_clients = 10
        self.max_subscriptions_per_client = 20
        self.max_topic_length = 256
        self.max_topic_levels = 8

        # Message size limits
        self.max_payload_size = 4096
        self.max_packet_size = 8192
        self.max_queued_messages = 50

        # QoS settings
        self.max_inflight = 10
        self.max_retained_messages = 100

        # Timeout and keep-alive
        self.connect_timeout = 10
        self.keep_alive_factor = 1.5
        self.no_keepalive_timeout = 3600

        # QoS retry settings
        self.qos_retry_interval = 10
        self.qos_max_retries = 3

        # Session management
        self.session_expiry = 3600

        # Feature flags
        self.allow_anonymous = True
        self.allow_zero_length_clientid = True
        self.retain_enabled = True
        self.qos2_enabled = True

        # System topics and stats
        self.sys_topics_enabled = True
        self.stats_interval = 60

        # Memory and performance
        self.recv_buffer_size = 1024
        self.gc_collect_interval = 30

        # Logging
        self.log_level = 'INFO'

        # Override defaults with provided kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def validate(self):
        """Validate configuration parameters.

        Raises:
            ValueError: If any parameter is invalid.
        """
        if not (1 <= self.port <= 65535):
            raise ValueError('port must be in range 1-65535, got %d' % self.port)

        if self.max_clients < 1:
            raise ValueError('max_clients must be >= 1, got %d' % self.max_clients)

        if self.max_payload_size < 1:
            raise ValueError('max_payload_size must be >= 1, got %d' % self.max_payload_size)

        if self.backlog < 1:
            raise ValueError('backlog must be >= 1, got %d' % self.backlog)

        if self.max_subscriptions_per_client < 1:
            raise ValueError('max_subscriptions_per_client must be >= 1, got %d' % self.max_subscriptions_per_client)

        if not (1 <= self.max_topic_length <= 65535):
            raise ValueError('max_topic_length must be in range 1-65535, got %d' % self.max_topic_length)

        if self.max_topic_levels < 1:
            raise ValueError('max_topic_levels must be >= 1, got %d' % self.max_topic_levels)

        if self.max_packet_size < self.max_payload_size:
            raise ValueError('max_packet_size must be >= max_payload_size')

        if self.max_queued_messages < 0:
            raise ValueError('max_queued_messages must be >= 0, got %d' % self.max_queued_messages)

        if self.max_inflight < 1:
            raise ValueError('max_inflight must be >= 1, got %d' % self.max_inflight)

        if self.max_retained_messages < 0:
            raise ValueError('max_retained_messages must be >= 0, got %d' % self.max_retained_messages)

        if self.connect_timeout < 1:
            raise ValueError('connect_timeout must be >= 1, got %d' % self.connect_timeout)

        if self.keep_alive_factor <= 0:
            raise ValueError('keep_alive_factor must be > 0, got %s' % self.keep_alive_factor)

        if self.no_keepalive_timeout < 1:
            raise ValueError('no_keepalive_timeout must be >= 1, got %d' % self.no_keepalive_timeout)

        if self.qos_retry_interval < 1:
            raise ValueError('qos_retry_interval must be >= 1, got %d' % self.qos_retry_interval)

        if self.qos_max_retries < 0:
            raise ValueError('qos_max_retries must be >= 0, got %d' % self.qos_max_retries)

        if self.session_expiry < 0:
            raise ValueError('session_expiry must be >= 0, got %d' % self.session_expiry)

        if self.stats_interval < 1:
            raise ValueError('stats_interval must be >= 1, got %d' % self.stats_interval)

        if self.recv_buffer_size < 64:
            raise ValueError('recv_buffer_size must be >= 64, got %d' % self.recv_buffer_size)

        if self.gc_collect_interval < 1:
            raise ValueError('gc_collect_interval must be >= 1, got %d' % self.gc_collect_interval)

        valid_levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        if self.log_level not in valid_levels:
            raise ValueError('log_level must be one of %s, got %s' % (valid_levels, self.log_level))
