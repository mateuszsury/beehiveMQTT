"""Broker statistics and $SYS topics for BeehiveMQTT."""

import gc
import time

class BrokerStats:
    """Tracks broker metrics and generates $SYS topic data."""
    __slots__ = (
        'messages_received', 'messages_sent',
        'publishes_received', 'publishes_sent',
        'bytes_received', 'bytes_sent',
        'connections_count', 'start_time',
        'version',
        '_conn_window_start', '_conn_window_count', '_conn_rate'
    )

    def __init__(self, version='1.0.0'):
        self.messages_received = 0
        self.messages_sent = 0
        self.publishes_received = 0
        self.publishes_sent = 0
        self.bytes_received = 0
        self.bytes_sent = 0
        self.connections_count = 0
        self.version = version
        try:
            self.start_time = time.ticks_ms()
        except AttributeError:
            self.start_time = int(time.time() * 1000)
        # Connection rate tracking (connections per minute)
        self._conn_window_start = self.start_time
        self._conn_window_count = 0
        self._conn_rate = 0

    def record_connection(self):
        """Record a new connection and update rate window."""
        self.connections_count += 1
        self._conn_window_count += 1

    def update_connection_rate(self):
        """Update connection rate. Call periodically (e.g. every 60s)."""
        try:
            now = time.ticks_ms()
            elapsed = time.ticks_diff(now, self._conn_window_start)
        except AttributeError:
            now = int(time.time() * 1000)
            elapsed = now - self._conn_window_start
        if elapsed >= 60000:  # 60 seconds
            self._conn_rate = self._conn_window_count
            self._conn_window_count = 0
            self._conn_window_start = now

    def get_uptime(self):
        try:
            return time.ticks_diff(time.ticks_ms(), self.start_time) // 1000
        except AttributeError:
            return (int(time.time() * 1000) - self.start_time) // 1000

    def get_sys_topics(self, connected_count, subscription_count, retained_count,
                       total_sessions=None):
        """Generate $SYS topic dict.

        Args:
            connected_count: Number of currently connected clients
            subscription_count: Total number of subscriptions
            retained_count: Number of retained messages
            total_sessions: Total number of sessions (connected + offline)
        """
        topics = {}
        topics['$SYS/broker/version'] = 'BeehiveMQTT %s' % self.version
        topics['$SYS/broker/uptime'] = str(self.get_uptime())
        topics['$SYS/broker/clients/connected'] = str(connected_count)
        if total_sessions is not None:
            topics['$SYS/broker/clients/total'] = str(total_sessions)
        topics['$SYS/broker/messages/received'] = str(self.messages_received)
        topics['$SYS/broker/messages/sent'] = str(self.messages_sent)
        topics['$SYS/broker/messages/publish/received'] = str(self.publishes_received)
        topics['$SYS/broker/messages/publish/sent'] = str(self.publishes_sent)
        topics['$SYS/broker/bytes/received'] = str(self.bytes_received)
        topics['$SYS/broker/bytes/sent'] = str(self.bytes_sent)
        topics['$SYS/broker/subscriptions/count'] = str(subscription_count)
        topics['$SYS/broker/messages/retained/count'] = str(retained_count)
        self.update_connection_rate()
        topics['$SYS/broker/load/connections'] = str(self._conn_rate)
        try:
            topics['$SYS/broker/heap/free'] = str(gc.mem_free())
            topics['$SYS/broker/heap/used'] = str(gc.mem_alloc())
        except (AttributeError, RuntimeError):
            pass
        return topics


class MemoryGuard:
    """Monitors memory and protects against OOM."""
    __slots__ = ('low_watermark', 'critical_watermark')

    OK = 0
    LOW = 1
    CRITICAL = 2

    def __init__(self, low_watermark=8192, critical_watermark=4096):
        self.low_watermark = low_watermark
        self.critical_watermark = critical_watermark

    def check(self):
        """Check memory level. Returns OK, LOW, or CRITICAL."""
        gc.collect()
        try:
            free = gc.mem_free()
        except (AttributeError, RuntimeError):
            return MemoryGuard.OK  # CPython fallback

        if free < self.critical_watermark:
            return MemoryGuard.CRITICAL
        elif free < self.low_watermark:
            return MemoryGuard.LOW
        return MemoryGuard.OK

    def trim_queues(self, sessions):
        """Trim message queues when memory is low."""
        for session in sessions.values():
            while len(session.pending_qos1) > 5:
                oldest_key = next(iter(session.pending_qos1))
                del session.pending_qos1[oldest_key]
            while len(session.pending_qos2_out) > 5:
                oldest_key = next(iter(session.pending_qos2_out))
                del session.pending_qos2_out[oldest_key]
            while len(session.queued_messages) > 10:
                session.queued_messages.pop(0)
