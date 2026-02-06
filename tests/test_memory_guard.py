"""Tests for beehivemqtt.stats.MemoryGuard."""

import pytest
from beehivemqtt.stats import MemoryGuard
from beehivemqtt.session import ClientSession
import micropython_compat


class TestMemoryGuardStates:
    """Test MemoryGuard memory state detection."""

    def test_ok_state(self):
        """Test OK state when plenty of memory available."""
        micropython_compat.set_mock_mem_free(50000)
        guard = MemoryGuard(low_watermark=8192, critical_watermark=4096)
        assert guard.check() == MemoryGuard.OK

    def test_low_state(self):
        """Test LOW state when memory below low watermark."""
        micropython_compat.set_mock_mem_free(5000)
        guard = MemoryGuard(low_watermark=8192, critical_watermark=4096)
        result = guard.check()
        assert result == MemoryGuard.LOW
        micropython_compat.set_mock_mem_free(50000)  # Reset

    def test_critical_state(self):
        """Test CRITICAL state when memory below critical watermark."""
        micropython_compat.set_mock_mem_free(2000)
        guard = MemoryGuard(low_watermark=8192, critical_watermark=4096)
        result = guard.check()
        assert result == MemoryGuard.CRITICAL
        micropython_compat.set_mock_mem_free(50000)  # Reset

    def test_exact_low_boundary(self):
        """Test at exact low watermark boundary."""
        micropython_compat.set_mock_mem_free(8192)
        guard = MemoryGuard(low_watermark=8192, critical_watermark=4096)
        result = guard.check()
        # At exactly low_watermark, free < low_watermark is False, so OK
        assert result == MemoryGuard.OK
        micropython_compat.set_mock_mem_free(50000)

    def test_exact_critical_boundary(self):
        """Test at exact critical watermark boundary."""
        micropython_compat.set_mock_mem_free(4096)
        guard = MemoryGuard(low_watermark=8192, critical_watermark=4096)
        result = guard.check()
        # At exactly critical_watermark, free < critical_watermark is False, so LOW
        assert result == MemoryGuard.LOW
        micropython_compat.set_mock_mem_free(50000)


class TestMemoryGuardTrimQueues:
    """Test MemoryGuard queue trimming."""

    def test_trim_qos1_queues(self):
        """Test trimming QoS1 pending messages."""
        guard = MemoryGuard()
        sessions = {}

        session = ClientSession('client1')
        # Add many pending QoS1 messages
        for i in range(20):
            session.pending_qos1[i + 1] = 'msg_%d' % i
        sessions['client1'] = session

        guard.trim_queues(sessions)

        # Should be trimmed to max 5
        assert len(session.pending_qos1) <= 5

    def test_trim_qos2_out_queues(self):
        """Test trimming QoS2 outbound pending messages."""
        guard = MemoryGuard()
        sessions = {}

        session = ClientSession('client1')
        for i in range(20):
            session.pending_qos2_out[i + 1] = 'msg_%d' % i
        sessions['client1'] = session

        guard.trim_queues(sessions)

        assert len(session.pending_qos2_out) <= 5

    def test_trim_queued_messages(self):
        """Test trimming offline queued messages."""
        guard = MemoryGuard()
        sessions = {}

        session = ClientSession('client1')
        for i in range(20):
            session.queued_messages.append((b'topic', b'payload', 1))
        sessions['client1'] = session

        guard.trim_queues(sessions)

        assert len(session.queued_messages) <= 10

    def test_trim_multiple_sessions(self):
        """Test trimming across multiple sessions."""
        guard = MemoryGuard()
        sessions = {}

        for cid in ['a', 'b', 'c']:
            session = ClientSession(cid)
            for i in range(15):
                session.pending_qos1[i + 1] = 'msg_%d' % i
            sessions[cid] = session

        guard.trim_queues(sessions)

        for cid in ['a', 'b', 'c']:
            assert len(sessions[cid].pending_qos1) <= 5

    def test_trim_no_sessions(self):
        """Test trimming with no sessions does not error."""
        guard = MemoryGuard()
        guard.trim_queues({})  # Should not raise

    def test_trim_session_already_under_limit(self):
        """Test trimming when session is already under limit."""
        guard = MemoryGuard()
        sessions = {}

        session = ClientSession('client1')
        session.pending_qos1[1] = 'msg1'
        session.pending_qos1[2] = 'msg2'
        sessions['client1'] = session

        guard.trim_queues(sessions)

        # Should remain unchanged
        assert len(session.pending_qos1) == 2


class TestMemoryGuardConstants:
    """Test MemoryGuard constants."""

    def test_state_constants(self):
        """Test state constant values."""
        assert MemoryGuard.OK == 0
        assert MemoryGuard.LOW == 1
        assert MemoryGuard.CRITICAL == 2

    def test_custom_watermarks(self):
        """Test custom watermark configuration."""
        guard = MemoryGuard(low_watermark=16384, critical_watermark=8192)
        assert guard.low_watermark == 16384
        assert guard.critical_watermark == 8192

    def test_has_slots(self):
        """Test __slots__ is defined."""
        assert hasattr(MemoryGuard, '__slots__')
