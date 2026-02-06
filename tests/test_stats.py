"""Tests for beehivemqtt.stats module."""

import pytest
import time
from beehivemqtt.stats import BrokerStats, MemoryGuard
from beehivemqtt.session import ClientSession


class TestBrokerStats:
    """Test BrokerStats class."""

    def test_initialization(self):
        """Test BrokerStats initialization."""
        stats = BrokerStats(version='1.2.3')

        assert stats.messages_received == 0
        assert stats.messages_sent == 0
        assert stats.publishes_received == 0
        assert stats.publishes_sent == 0
        assert stats.bytes_received == 0
        assert stats.bytes_sent == 0
        assert stats.connections_count == 0
        assert stats.version == '1.2.3'
        assert stats.start_time > 0

    def test_increment_counters(self):
        """Test incrementing stat counters."""
        stats = BrokerStats()

        stats.messages_received += 5
        stats.messages_sent += 3
        stats.publishes_received += 2
        stats.publishes_sent += 1
        stats.bytes_received += 1024
        stats.bytes_sent += 512
        stats.connections_count += 10

        assert stats.messages_received == 5
        assert stats.messages_sent == 3
        assert stats.publishes_received == 2
        assert stats.publishes_sent == 1
        assert stats.bytes_received == 1024
        assert stats.bytes_sent == 512
        assert stats.connections_count == 10

    def test_get_uptime_returns_positive(self):
        """Test get_uptime returns positive number."""
        stats = BrokerStats()

        # Wait a tiny bit
        time.sleep(0.01)

        uptime = stats.get_uptime()
        assert uptime >= 0

    def test_get_uptime_increases(self):
        """Test get_uptime increases over time."""
        stats = BrokerStats()

        uptime1 = stats.get_uptime()
        time.sleep(1.1)
        uptime2 = stats.get_uptime()

        assert uptime2 > uptime1

    def test_get_sys_topics_returns_dict(self):
        """Test get_sys_topics returns expected dictionary."""
        stats = BrokerStats(version='1.0.0')
        stats.messages_received = 100
        stats.messages_sent = 50
        stats.publishes_received = 80
        stats.publishes_sent = 40

        sys_topics = stats.get_sys_topics(
            connected_count=5,
            subscription_count=20,
            retained_count=10
        )

        assert '$SYS/broker/version' in sys_topics
        assert sys_topics['$SYS/broker/version'] == 'BeehiveMQTT 1.0.0'
        assert '$SYS/broker/uptime' in sys_topics
        assert '$SYS/broker/clients/connected' in sys_topics
        assert sys_topics['$SYS/broker/clients/connected'] == '5'
        assert '$SYS/broker/messages/received' in sys_topics
        assert sys_topics['$SYS/broker/messages/received'] == '100'
        assert '$SYS/broker/messages/sent' in sys_topics
        assert sys_topics['$SYS/broker/messages/sent'] == '50'
        assert '$SYS/broker/messages/publish/received' in sys_topics
        assert sys_topics['$SYS/broker/messages/publish/received'] == '80'
        assert '$SYS/broker/messages/publish/sent' in sys_topics
        assert sys_topics['$SYS/broker/messages/publish/sent'] == '40'
        assert '$SYS/broker/subscriptions/count' in sys_topics
        assert sys_topics['$SYS/broker/subscriptions/count'] == '20'
        assert '$SYS/broker/messages/retained/count' in sys_topics
        assert sys_topics['$SYS/broker/messages/retained/count'] == '10'

    def test_get_sys_topics_includes_memory_on_micropython(self):
        """Test get_sys_topics includes memory stats when available."""
        stats = BrokerStats()

        sys_topics = stats.get_sys_topics(
            connected_count=1,
            subscription_count=1,
            retained_count=1
        )

        # On CPython with our mock, these should be present
        assert '$SYS/broker/heap/free' in sys_topics
        assert '$SYS/broker/heap/used' in sys_topics

    def test_get_sys_topics_includes_total_sessions(self):
        """Test get_sys_topics includes total sessions when provided."""
        stats = BrokerStats()

        sys_topics = stats.get_sys_topics(
            connected_count=3,
            subscription_count=5,
            retained_count=2,
            total_sessions=10
        )

        assert '$SYS/broker/clients/total' in sys_topics
        assert sys_topics['$SYS/broker/clients/total'] == '10'

    def test_get_sys_topics_without_total_sessions(self):
        """Test get_sys_topics omits total sessions when not provided."""
        stats = BrokerStats()

        sys_topics = stats.get_sys_topics(
            connected_count=3,
            subscription_count=5,
            retained_count=2
        )

        assert '$SYS/broker/clients/total' not in sys_topics

    def test_get_sys_topics_includes_bytes(self):
        """Test get_sys_topics includes bytes received and sent keys."""
        stats = BrokerStats()
        stats.bytes_received = 4096
        stats.bytes_sent = 2048

        sys_topics = stats.get_sys_topics(
            connected_count=1,
            subscription_count=1,
            retained_count=0
        )

        assert '$SYS/broker/bytes/received' in sys_topics
        assert '$SYS/broker/bytes/sent' in sys_topics
        assert sys_topics['$SYS/broker/bytes/received'] == '4096'
        assert sys_topics['$SYS/broker/bytes/sent'] == '2048'

    def test_get_sys_topics_includes_load_connections(self):
        """Test get_sys_topics includes load connections rate key."""
        stats = BrokerStats()
        # Record some connections then trigger rate update
        for _ in range(5):
            stats.record_connection()
        # Force window to expire by backdating window start
        stats._conn_window_start = stats._conn_window_start - 61000

        sys_topics = stats.get_sys_topics(
            connected_count=5,
            subscription_count=10,
            retained_count=3
        )

        assert '$SYS/broker/load/connections' in sys_topics
        assert sys_topics['$SYS/broker/load/connections'] == '5'


class TestMemoryGuard:
    """Test MemoryGuard class."""

    def test_initialization(self):
        """Test MemoryGuard initialization."""
        guard = MemoryGuard(low_watermark=10000, critical_watermark=5000)

        assert guard.low_watermark == 10000
        assert guard.critical_watermark == 5000

    def test_check_returns_ok_on_cpython(self):
        """Test check returns OK on CPython (mock returns high value)."""
        guard = MemoryGuard()

        status = guard.check()

        # CPython mock returns OK
        assert status == MemoryGuard.OK

    def test_constants(self):
        """Test MemoryGuard status constants."""
        assert MemoryGuard.OK == 0
        assert MemoryGuard.LOW == 1
        assert MemoryGuard.CRITICAL == 2

    def test_trim_queues_removes_from_pending_qos1(self):
        """Test trim_queues removes entries from pending_qos1."""
        guard = MemoryGuard()
        sessions = {}

        session = ClientSession('client1')
        # Add many QoS1 entries
        for i in range(10):
            session.pending_qos1[i] = f"message_{i}"
        sessions['client1'] = session

        guard.trim_queues(sessions)

        # Should be trimmed to max 5
        assert len(session.pending_qos1) <= 5

    def test_trim_queues_removes_from_queued_messages(self):
        """Test trim_queues removes entries from queued_messages."""
        guard = MemoryGuard()
        sessions = {}

        session = ClientSession('client1')
        # Add many queued messages
        for i in range(20):
            session.queued_messages.append((f'topic{i}'.encode(), b'data', 0))
        sessions['client1'] = session

        guard.trim_queues(sessions)

        # Should be trimmed to max 10
        assert len(session.queued_messages) <= 10

    def test_trim_queues_handles_multiple_sessions(self):
        """Test trim_queues processes multiple sessions."""
        guard = MemoryGuard()
        sessions = {}

        session1 = ClientSession('client1')
        for i in range(10):
            session1.pending_qos1[i] = f"msg{i}"
        sessions['client1'] = session1

        session2 = ClientSession('client2')
        for i in range(15):
            session2.queued_messages.append((b'topic', b'data', 0))
        sessions['client2'] = session2

        guard.trim_queues(sessions)

        assert len(session1.pending_qos1) <= 5
        assert len(session2.queued_messages) <= 10

    def test_trim_queues_trims_pending_qos2_out(self):
        """Test trim_queues removes entries from pending_qos2_out."""
        guard = MemoryGuard()
        sessions = {}

        session = ClientSession('client1')
        # Add many QoS2 outbound entries
        for i in range(10):
            session.pending_qos2_out[i] = "msg_%d" % i
        sessions['client1'] = session

        guard.trim_queues(sessions)

        # Should be trimmed to max 5
        assert len(session.pending_qos2_out) <= 5
