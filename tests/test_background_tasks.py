"""Tests for broker background tasks."""

import gc
import time
import pytest
from unittest.mock import patch, MagicMock

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

from beehivemqtt.broker import MQTTBroker
from beehivemqtt.config import BrokerConfig
from beehivemqtt.session import ClientSession
from beehivemqtt.qos import QoS1Outbound, QoS2Outbound


class TestGcTask:
    """Test garbage collection background task."""

    @pytest.mark.asyncio
    async def test_gc_collect_called(self, configured_broker):
        """Test that gc.collect() is called during GC task."""
        broker = configured_broker
        broker._running = True

        # Mock gc.collect to track calls
        with patch('gc.collect') as mock_collect:
            # Run GC task for one iteration by patching asyncio.sleep
            call_count = [0]
            original_sleep = asyncio.sleep

            async def mock_sleep(t):
                call_count[0] += 1
                if call_count[0] >= 1:
                    broker._running = False
                await original_sleep(0)

            with patch('asyncio.sleep', mock_sleep):
                try:
                    await asyncio.wait_for(broker._gc_task(), timeout=2)
                except asyncio.TimeoutError:
                    pass

            # Verify gc.collect() was called at least once
            assert mock_collect.call_count >= 1

    @pytest.mark.asyncio
    async def test_gc_threshold_called(self, configured_broker):
        """Test that gc.threshold() is called if available (MicroPython only)."""
        broker = configured_broker
        broker._running = True

        # Mock gc functions - create gc.threshold if it doesn't exist
        with patch('gc.collect') as mock_collect:
            # Only test if gc.threshold exists (MicroPython)
            if hasattr(gc, 'threshold'):
                with patch('gc.threshold') as mock_threshold:
                    with patch('gc.mem_alloc', return_value=10000):
                        # Run GC task for one iteration
                        call_count = [0]
                        original_sleep = asyncio.sleep

                        async def mock_sleep(t):
                            call_count[0] += 1
                            if call_count[0] >= 1:
                                broker._running = False
                            await original_sleep(0)

                        with patch('asyncio.sleep', mock_sleep):
                            try:
                                await asyncio.wait_for(broker._gc_task(), timeout=2)
                            except asyncio.TimeoutError:
                                pass

                        # Verify gc.threshold() was called
                        assert mock_threshold.call_count >= 1
                        # Should be called with mem_alloc() + 4096
                        mock_threshold.assert_called_with(10000 + 4096)
            else:
                # On CPython, just verify gc.collect() was called and task ran
                call_count = [0]
                original_sleep = asyncio.sleep

                async def mock_sleep(t):
                    call_count[0] += 1
                    if call_count[0] >= 1:
                        broker._running = False
                    await original_sleep(0)

                with patch('asyncio.sleep', mock_sleep):
                    try:
                        await asyncio.wait_for(broker._gc_task(), timeout=2)
                    except asyncio.TimeoutError:
                        pass

                assert mock_collect.call_count >= 1


class TestKeepAliveMonitor:
    """Test keep-alive monitoring background task."""

    @pytest.mark.asyncio
    async def test_expired_client_disconnected(self, configured_broker, mock_writer):
        """Test that session with expired keep_alive is disconnected."""
        broker = configured_broker

        # Create session with expired keep-alive
        session = ClientSession('expired-client', clean_session=True)
        session.connected = True
        session.keep_alive = 1  # 1 second
        session.writer = mock_writer
        # Set last_activity to a time that's definitely expired
        try:
            current = time.ticks_ms()
            # Subtract 2000ms (2 seconds) which is > keep_alive * 1.5 (1.5s)
            session.last_activity = current - 2000
        except AttributeError:
            # CPython fallback
            current = int(time.time() * 1000)
            session.last_activity = current - 2000
        broker.sessions['expired-client'] = session

        # Mock _handle_disconnect to verify it's called
        disconnect_calls = []

        async def mock_disconnect(sess, graceful):
            disconnect_calls.append((sess.client_id, graceful))
            sess.connected = False

        broker._handle_disconnect = mock_disconnect

        # Run keep-alive monitor for one check cycle
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._keep_alive_monitor(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify disconnect was called for expired client
        assert len(disconnect_calls) == 1
        assert disconnect_calls[0] == ('expired-client', False)

    @pytest.mark.asyncio
    async def test_active_client_not_disconnected(self, configured_broker, mock_writer):
        """Test that recently active session is not disconnected."""
        broker = configured_broker

        # Create session with recent activity
        session = ClientSession('active-client', clean_session=True)
        session.connected = True
        session.keep_alive = 10
        session.writer = mock_writer
        session.update_activity()  # Set to current time
        broker.sessions['active-client'] = session

        disconnect_calls = []

        async def mock_disconnect(sess, graceful):
            disconnect_calls.append((sess.client_id, graceful))

        broker._handle_disconnect = mock_disconnect

        # Run keep-alive monitor for one check
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._keep_alive_monitor(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify disconnect was NOT called
        assert len(disconnect_calls) == 0
        assert session.connected is True

    @pytest.mark.asyncio
    async def test_keepalive_zero_not_checked(self, configured_broker, mock_writer):
        """Test that session with keep_alive=0 is not disconnected."""
        broker = configured_broker

        # Create session with keep_alive disabled
        session = ClientSession('no-keepalive', clean_session=True)
        session.connected = True
        session.keep_alive = 0  # Disabled
        session.writer = mock_writer
        session.last_activity = 0  # Old activity
        broker.sessions['no-keepalive'] = session

        disconnect_calls = []

        async def mock_disconnect(sess, graceful):
            disconnect_calls.append(sess.client_id)

        broker._handle_disconnect = mock_disconnect

        # Run keep-alive monitor
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._keep_alive_monitor(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify disconnect was NOT called
        assert len(disconnect_calls) == 0

    @pytest.mark.asyncio
    async def test_multiple_clients_checked(self, configured_broker, mock_writer):
        """Test that mix of active/expired clients are handled correctly."""
        broker = configured_broker

        # Create active client
        active = ClientSession('active', clean_session=True)
        active.connected = True
        active.keep_alive = 10
        active.writer = mock_writer
        active.update_activity()
        broker.sessions['active'] = active

        # Create expired client
        expired = ClientSession('expired', clean_session=True)
        expired.connected = True
        expired.keep_alive = 1  # 1 second
        expired.writer = mock_writer
        # Set to expired time
        try:
            current = time.ticks_ms()
            expired.last_activity = current - 2000  # 2 seconds ago
        except AttributeError:
            current = int(time.time() * 1000)
            expired.last_activity = current - 2000
        broker.sessions['expired'] = expired

        # Create client with keep_alive disabled
        no_ka = ClientSession('no-ka', clean_session=True)
        no_ka.connected = True
        no_ka.keep_alive = 0
        no_ka.writer = mock_writer
        no_ka.last_activity = 0
        broker.sessions['no-ka'] = no_ka

        disconnect_calls = []

        async def mock_disconnect(sess, graceful):
            disconnect_calls.append(sess.client_id)
            sess.connected = False

        broker._handle_disconnect = mock_disconnect

        # Run keep-alive monitor
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._keep_alive_monitor(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify only expired client was disconnected
        assert len(disconnect_calls) == 1
        assert 'expired' in disconnect_calls
        assert active.connected is True
        assert no_ka.connected is True


class TestRetransmitTask:
    """Test QoS retransmission background task."""

    @pytest.mark.asyncio
    async def test_retransmit_qos1_with_dup(self, configured_broker, mock_writer):
        """Test that pending QoS1 past retry interval is retransmitted with DUP flag."""
        broker = configured_broker
        broker.config.qos_retry_interval = 1  # 1 second

        # Create session with pending QoS1
        session = ClientSession('client1', clean_session=True)
        session.connected = True
        session.writer = mock_writer
        broker.sessions['client1'] = session

        # Add pending QoS1 message with old timestamp
        entry = QoS1Outbound(packet_id=42, topic=b'test/topic', payload=b'data', qos=1)
        # Set timestamp to be past the retry interval
        try:
            current = time.ticks_ms()
            entry.timestamp = current - 1100  # 1.1 seconds ago
        except AttributeError:
            current = int(time.time() * 1000)
            entry.timestamp = current - 1100
        entry.retry_count = 0
        session.pending_qos1[42] = entry

        # Run retransmit task once
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._retransmit_task(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify message was retransmitted
        assert len(mock_writer.data) > 0
        # Check DUP flag is set (bit 3 of first byte)
        first_byte = mock_writer.data[0]
        dup_flag = (first_byte & 0x08) != 0
        assert dup_flag is True

        # Verify retry count incremented
        assert entry.retry_count == 1

    @pytest.mark.asyncio
    async def test_drop_after_max_retries(self, configured_broker, mock_writer):
        """Test that QoS1 at max retries is removed from pending."""
        broker = configured_broker
        broker.config.qos_retry_interval = 1  # 1 second
        broker.config.qos_max_retries = 3

        # Create session with pending QoS1 at max retries
        session = ClientSession('client1', clean_session=True)
        session.connected = True
        session.writer = mock_writer
        broker.sessions['client1'] = session

        # Add pending QoS1 at max retries
        entry = QoS1Outbound(packet_id=99, topic=b'test', payload=b'data', qos=1)
        # Set to old timestamp past retry interval
        try:
            current = time.ticks_ms()
            entry.timestamp = current - 1100
        except AttributeError:
            current = int(time.time() * 1000)
            entry.timestamp = current - 1100
        entry.retry_count = 3  # At max
        session.pending_qos1[99] = entry

        # Run retransmit task
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._retransmit_task(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify entry was removed
        assert 99 not in session.pending_qos1

    @pytest.mark.asyncio
    async def test_retransmit_qos2_pubrel(self, configured_broker, mock_writer):
        """Test that QoS2 outbound in AWAITING_PUBCOMP state retransmits PUBREL."""
        broker = configured_broker
        broker.config.qos_retry_interval = 1  # 1 second

        # Create session with QoS2 outbound awaiting PUBCOMP
        session = ClientSession('client1', clean_session=True)
        session.connected = True
        session.writer = mock_writer
        broker.sessions['client1'] = session

        # Add QoS2 outbound in AWAITING_PUBCOMP state
        entry = QoS2Outbound(packet_id=50, topic=b'qos2/topic', payload=b'payload')
        entry.state = QoS2Outbound.AWAITING_PUBCOMP
        # Set to old timestamp past retry interval
        try:
            current = time.ticks_ms()
            entry.timestamp = current - 1100
        except AttributeError:
            current = int(time.time() * 1000)
            entry.timestamp = current - 1100
        entry.retry_count = 0
        session.pending_qos2_out[50] = entry

        # Run retransmit task
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._retransmit_task(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify PUBREL was sent (packet type 0x62)
        assert len(mock_writer.data) > 0
        first_byte = mock_writer.data[0]
        packet_type = (first_byte >> 4)
        assert packet_type == 6  # PUBREL

        # Verify retry count incremented
        assert entry.retry_count == 1


class TestSessionCleanupTask:
    """Test session cleanup background task."""

    @pytest.mark.asyncio
    async def test_expired_offline_session_removed(self, configured_broker):
        """Test that offline session past session_expiry is removed."""
        broker = configured_broker
        broker.config.session_expiry = 1  # 1 second

        # Create expired offline session
        session = ClientSession('offline', clean_session=False)
        session.connected = False
        # Set to old activity past expiry
        try:
            current = time.ticks_ms()
            session.last_activity = current - 1100  # 1.1 seconds ago
        except AttributeError:
            current = int(time.time() * 1000)
            session.last_activity = current - 1100
        broker.sessions['offline'] = session

        # Run session cleanup task
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._session_cleanup_task(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify session was removed
        assert 'offline' not in broker.sessions

    @pytest.mark.asyncio
    async def test_active_session_not_removed(self, configured_broker):
        """Test that connected session is not removed."""
        broker = configured_broker

        # Create active connected session
        session = ClientSession('active', clean_session=False)
        session.connected = True
        session.update_activity()
        broker.sessions['active'] = session

        # Run session cleanup
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._session_cleanup_task(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify session was NOT removed
        assert 'active' in broker.sessions

    @pytest.mark.asyncio
    async def test_prune_called(self, configured_broker):
        """Test that topic_tree.prune() is called during cleanup."""
        broker = configured_broker

        # Mock topic_tree.prune()
        prune_calls = [0]
        original_prune = broker.topic_tree.prune

        def mock_prune():
            prune_calls[0] += 1
            return original_prune()

        broker.topic_tree.prune = mock_prune

        # Run session cleanup
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._session_cleanup_task(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify prune was called
        assert prune_calls[0] >= 1


class TestSysTopicsTask:
    """Test $SYS topics publishing background task."""

    @pytest.mark.asyncio
    async def test_sys_topics_published(self, configured_broker):
        """Test that $SYS topics are published via router."""
        # Enable $SYS topics
        configured_broker.config.sys_topics_enabled = True
        configured_broker.config.stats_interval = 0.001  # 1ms

        broker = configured_broker

        # Mock router.route_publish to capture calls
        publish_calls = []

        async def mock_route_publish(topic, payload, qos, retain, sender_id):
            publish_calls.append((topic, payload, qos, retain, sender_id))

        broker.router.route_publish = mock_route_publish

        # Run $SYS topics task
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._sys_topics_task(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Verify $SYS topics were published
        assert len(publish_calls) > 0

        # Check that topics start with '$SYS'
        for topic, payload, qos, retain, sender_id in publish_calls:
            topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
            assert topic_str.startswith('$SYS')
            assert qos == 0
            assert retain is True
            assert sender_id is None

    @pytest.mark.asyncio
    async def test_all_sys_topics_present(self, configured_broker):
        """Test that all expected $SYS topic keys are published."""
        configured_broker.config.sys_topics_enabled = True
        configured_broker.config.stats_interval = 0.001

        broker = configured_broker

        # Mock router.route_publish
        publish_calls = []

        async def mock_route_publish(topic, payload, qos, retain, sender_id):
            publish_calls.append((topic, payload, qos, retain, sender_id))

        broker.router.route_publish = mock_route_publish

        # Run $SYS topics task
        broker._running = True
        call_count = [0]
        original_sleep = asyncio.sleep

        async def mock_sleep(t):
            call_count[0] += 1
            if call_count[0] >= 1:
                broker._running = False
            await original_sleep(0)

        with patch('asyncio.sleep', mock_sleep):
            try:
                await asyncio.wait_for(broker._sys_topics_task(), timeout=2)
            except asyncio.TimeoutError:
                pass

        # Extract published topic names
        topics = [
            t[0].decode('utf-8') if isinstance(t[0], bytes) else t[0]
            for t in publish_calls
        ]

        # Verify expected topics are present
        expected_keywords = ['uptime', 'clients', 'messages', 'bytes', 'subscriptions']
        for keyword in expected_keywords:
            found = any(keyword in topic for topic in topics)
            assert found, "Expected $SYS topic with '%s' not found" % keyword

    @pytest.mark.asyncio
    async def test_sys_disabled_no_publish(self):
        """Test that sys_topics_enabled=False prevents task from starting."""
        config = BrokerConfig(
            port=1883,
            sys_topics_enabled=False,
            log_level='ERROR'
        )
        broker = MQTTBroker(config=config)

        # Mock router.route_publish
        publish_calls = []

        async def mock_route_publish(topic, payload, qos, retain, sender_id):
            publish_calls.append(topic)

        broker.router.route_publish = mock_route_publish

        # Start serve() in background
        serve_task = asyncio.create_task(broker.serve())

        # Wait a bit
        await asyncio.sleep(0.1)

        # Shutdown
        await broker.shutdown()

        try:
            await serve_task
        except:
            pass

        # Verify no $SYS topics were published
        sys_topics = [t for t in publish_calls if b'$SYS' in t or '$SYS' in str(t)]
        assert len(sys_topics) == 0
