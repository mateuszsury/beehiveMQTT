"""Tests for beehivemqtt.session module."""

import pytest
import time
from beehivemqtt.session import ClientSession, SessionManager
from beehivemqtt.config import BrokerConfig


class TestClientSession:
    """Test ClientSession class."""

    def test_initialization_clean_session(self):
        """Test ClientSession initialization with clean session."""
        session = ClientSession('client1', clean_session=True)

        assert session.client_id == 'client1'
        assert session.clean_session is True
        assert session.connected is False
        assert session.subscriptions == {}
        assert session.keep_alive == 0
        assert session.packet_id_counter == 0
        assert session.pending_qos1 == {}
        assert session.pending_qos2 == {}
        assert session.queued_messages == []

    def test_initialization_persistent_session(self):
        """Test ClientSession initialization with persistent session."""
        session = ClientSession('client2', clean_session=False)

        assert session.client_id == 'client2'
        assert session.clean_session is False

    def test_next_packet_id_starts_at_one(self):
        """Test next_packet_id starts at 1."""
        session = ClientSession('client1')

        packet_id = session.next_packet_id()
        assert packet_id == 1

    def test_next_packet_id_increments(self):
        """Test next_packet_id increments correctly."""
        session = ClientSession('client1')

        ids = [session.next_packet_id() for _ in range(5)]
        assert ids == [1, 2, 3, 4, 5]

    def test_next_packet_id_wraps_from_65535_to_1(self):
        """Test next_packet_id wraps from 65535 to 1."""
        session = ClientSession('client1')
        session.packet_id_counter = 65534

        assert session.next_packet_id() == 65535
        assert session.next_packet_id() == 1
        assert session.next_packet_id() == 2

    def test_update_activity_sets_timestamp(self):
        """Test update_activity sets last_activity timestamp."""
        session = ClientSession('client1')
        assert session.last_activity == 0

        session.update_activity()
        assert session.last_activity > 0

    def test_is_keep_alive_expired_disabled_when_zero(self):
        """Test keep-alive expiration is disabled when keep_alive=0."""
        session = ClientSession('client1')
        session.keep_alive = 0
        session.update_activity()

        assert session.is_keep_alive_expired() is False

    def test_is_keep_alive_not_expired_when_recent(self):
        """Test keep-alive not expired when activity is recent."""
        session = ClientSession('client1')
        session.keep_alive = 10  # 10 seconds
        session.update_activity()

        assert session.is_keep_alive_expired(factor=1.5) is False

    def test_is_keep_alive_expired_when_timeout(self):
        """Test keep-alive expired when timeout exceeded."""
        session = ClientSession('client1')
        session.keep_alive = 1  # 1 second
        # Set activity to old timestamp
        session.last_activity = time.ticks_ms() - 2000  # 2 seconds ago

        # With factor 1.5, timeout is 1.5 seconds, so 2 seconds should expire
        assert session.is_keep_alive_expired(factor=1.5) is True

    def test_queue_message_appends_to_queue(self):
        """Test queue_message appends message to queue."""
        session = ClientSession('client1')

        session.queue_message(b'topic1', b'payload1', qos=1)
        session.queue_message(b'topic2', b'payload2', qos=0)

        assert len(session.queued_messages) == 2
        assert session.queued_messages[0] == (b'topic1', b'payload1', 1)
        assert session.queued_messages[1] == (b'topic2', b'payload2', 0)

    def test_queue_message_fifo_eviction_at_limit(self):
        """Test queue_message uses FIFO eviction when at max."""
        session = ClientSession('client1')

        # Queue 3 messages with max_queued=2
        session.queue_message(b'topic1', b'payload1', qos=0, max_queued=2)
        session.queue_message(b'topic2', b'payload2', qos=0, max_queued=2)
        session.queue_message(b'topic3', b'payload3', qos=0, max_queued=2)

        # Should only have last 2 messages
        assert len(session.queued_messages) == 2
        assert session.queued_messages[0] == (b'topic2', b'payload2', 0)
        assert session.queued_messages[1] == (b'topic3', b'payload3', 0)

    def test_get_queued_messages_returns_and_clears(self):
        """Test get_queued_messages returns messages and clears queue."""
        session = ClientSession('client1')

        session.queue_message(b'topic1', b'payload1', qos=1)
        session.queue_message(b'topic2', b'payload2', qos=0)

        messages = session.get_queued_messages()

        assert len(messages) == 2
        assert messages[0] == (b'topic1', b'payload1', 1)
        assert messages[1] == (b'topic2', b'payload2', 0)

        # Queue should be empty now
        assert session.queued_messages == []

    def test_get_queued_messages_empty_queue(self):
        """Test get_queued_messages on empty queue."""
        session = ClientSession('client1')

        messages = session.get_queued_messages()
        assert messages == []

    @pytest.mark.asyncio
    async def test_send_writes_to_writer(self, client_session):
        """Test send method writes data to writer."""
        await client_session.send(b'test data')

        assert client_session.writer.get_data() == b'test data'

    @pytest.mark.asyncio
    async def test_send_marks_disconnected_on_error(self, client_session):
        """Test send marks session as disconnected on OSError."""
        # Close writer to simulate error
        client_session.writer.close()

        await client_session.send(b'test')

        # Should mark as disconnected
        assert client_session.connected is False


class TestSessionManager:
    """Test SessionManager class."""

    def test_get_or_create_clean_session(self):
        """Test get_or_create with clean_session=True."""
        sessions = {}
        config = BrokerConfig()
        manager = SessionManager(sessions, config)

        session, session_present = manager.get_or_create('client1', clean_session=True)

        assert session is not None
        assert session.client_id == 'client1'
        assert session.clean_session is True
        assert session_present is False
        # Clean session should not be stored
        assert 'client1' not in sessions

    def test_get_or_create_persistent_new(self):
        """Test get_or_create with persistent session (new)."""
        sessions = {}
        config = BrokerConfig()
        manager = SessionManager(sessions, config)

        session, session_present = manager.get_or_create('client1', clean_session=False)

        assert session is not None
        assert session.clean_session is False
        assert session_present is False

    def test_get_or_create_persistent_existing(self):
        """Test get_or_create with persistent session (existing)."""
        sessions = {}
        config = BrokerConfig()
        manager = SessionManager(sessions, config)

        # Create initial session
        session1, _ = manager.get_or_create('client1', clean_session=False)
        sessions['client1'] = session1

        # Get existing session
        session2, session_present = manager.get_or_create('client1', clean_session=False)

        assert session2 is session1
        assert session_present is True

    def test_remove_session(self):
        """Test removing a session."""
        sessions = {'client1': ClientSession('client1')}
        config = BrokerConfig()
        manager = SessionManager(sessions, config)

        manager.remove('client1')

        assert 'client1' not in sessions

    def test_remove_nonexistent_session(self):
        """Test removing non-existent session (no error)."""
        sessions = {}
        config = BrokerConfig()
        manager = SessionManager(sessions, config)

        # Should not raise error
        manager.remove('nonexistent')

    def test_cleanup_expired_removes_old_sessions(self):
        """Test cleanup_expired removes old offline sessions."""
        sessions = {}
        config = BrokerConfig(session_expiry=1)  # 1 second expiry
        manager = SessionManager(sessions, config)

        # Create session and mark as old
        session = ClientSession('client1', clean_session=False)
        session.connected = False
        session.last_activity = time.ticks_ms() - 2000  # 2 seconds ago
        sessions['client1'] = session

        removed = manager.cleanup_expired()

        assert removed == 1
        assert 'client1' not in sessions

    def test_cleanup_expired_keeps_recent_sessions(self):
        """Test cleanup_expired keeps recent offline sessions."""
        sessions = {}
        config = BrokerConfig(session_expiry=10)  # 10 seconds expiry
        manager = SessionManager(sessions, config)

        # Create recent session
        session = ClientSession('client1', clean_session=False)
        session.connected = False
        session.update_activity()
        sessions['client1'] = session

        removed = manager.cleanup_expired()

        assert removed == 0
        assert 'client1' in sessions

    def test_cleanup_expired_keeps_connected_sessions(self):
        """Test cleanup_expired keeps connected sessions even if old."""
        sessions = {}
        config = BrokerConfig(session_expiry=1)
        manager = SessionManager(sessions, config)

        # Create old but connected session
        session = ClientSession('client1', clean_session=False)
        session.connected = True
        session.last_activity = time.ticks_ms() - 2000
        sessions['client1'] = session

        removed = manager.cleanup_expired()

        assert removed == 0
        assert 'client1' in sessions

    def test_cleanup_expired_keeps_clean_sessions(self):
        """Test cleanup_expired only removes persistent sessions."""
        sessions = {}
        config = BrokerConfig(session_expiry=1)
        manager = SessionManager(sessions, config)

        # Create old clean session (should not be removed)
        session = ClientSession('client1', clean_session=True)
        session.connected = False
        session.last_activity = time.ticks_ms() - 2000
        sessions['client1'] = session

        removed = manager.cleanup_expired()

        # Clean sessions are handled differently (not by expiry)
        assert removed == 0

    def test_get_connected_count_empty(self):
        """Test get_connected_count on empty sessions."""
        sessions = {}
        config = BrokerConfig()
        manager = SessionManager(sessions, config)

        assert manager.get_connected_count() == 0

    def test_get_connected_count_mixed(self):
        """Test get_connected_count with mix of connected and disconnected."""
        sessions = {}
        config = BrokerConfig()
        manager = SessionManager(sessions, config)

        session1 = ClientSession('client1')
        session1.connected = True
        sessions['client1'] = session1

        session2 = ClientSession('client2')
        session2.connected = False
        sessions['client2'] = session2

        session3 = ClientSession('client3')
        session3.connected = True
        sessions['client3'] = session3

        assert manager.get_connected_count() == 2
