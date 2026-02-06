"""
Client session management for BeehiveMQTT.

This module handles individual MQTT client sessions including:
- Connection state tracking
- Subscription management
- Keep-alive monitoring
- Will message storage
- Packet ID generation
"""

import time
try:
    import asyncio
except ImportError:
    import uasyncio as asyncio


class ClientSession:
    """
    Represents a single MQTT client session.

    Tracks connection state, subscriptions, keep-alive timing, and will message.
    Provides thread-safe message sending with write lock.
    """

    __slots__ = (
        'client_id', 'clean_session', 'connected', 'subscriptions',
        'keep_alive', 'last_activity',
        'will_topic', 'will_message', 'will_qos', 'will_retain',
        'username', 'reader', 'writer',
        'packet_id_counter', '_write_lock',
        'pending_qos1', 'pending_qos2', 'pending_qos2_out',
        'queued_messages'
    )

    def __init__(self, client_id, clean_session=True):
        """
        Initialize a new client session.

        Args:
            client_id: Unique client identifier string
            clean_session: If True, discard state on disconnect
        """
        self.client_id = client_id
        self.clean_session = clean_session
        self.connected = False
        self.subscriptions = {}  # topic_filter -> granted_qos

        # Keep-alive tracking
        self.keep_alive = 0
        self.last_activity = 0

        # Will message (Last Will and Testament)
        self.will_topic = None
        self.will_message = None
        self.will_qos = 0
        self.will_retain = False

        # Authentication
        self.username = None

        # Network streams (set when client connects)
        self.reader = None
        self.writer = None

        # Packet ID for QoS messages (1-65535)
        self.packet_id_counter = 0

        # Write lock for thread-safe sending (lazy init)
        self._write_lock = None

        # QoS message tracking
        self.pending_qos1 = {}  # packet_id -> QoS1Outbound
        self.pending_qos2 = {}  # packet_id -> QoS2Inbound
        self.pending_qos2_out = {}  # packet_id -> QoS2Outbound
        self.queued_messages = []  # messages waiting to be sent

    def next_packet_id(self):
        """
        Generate next packet identifier for QoS 1/2 messages.

        Packet IDs are in range 1-65535 (0x0001-0xFFFF).
        Counter wraps from 65535 back to 1.

        Returns:
            int: Next packet ID (1-65535)
        """
        self.packet_id_counter += 1
        if self.packet_id_counter > 65535:
            self.packet_id_counter = 1
        return self.packet_id_counter

    async def send(self, data):
        """
        Send data to client with write lock protection.

        Lazily creates write lock on first use to save RAM.
        Sets connected=False on OSError (client disconnected).

        Args:
            data: Bytes to send to client
        """
        # Lazy lock creation - only create when needed
        if self._write_lock is None:
            self._write_lock = asyncio.Lock()

        try:
            async with self._write_lock:
                self.writer.write(data)
                await self.writer.drain()
        except OSError:
            # Client disconnected - mark as not connected
            self.connected = False

    def update_activity(self):
        """
        Update last activity timestamp to current time.

        Uses time.ticks_ms() on MicroPython for efficient timing.
        Falls back to time.time() * 1000 on CPython.
        """
        try:
            self.last_activity = time.ticks_ms()
        except AttributeError:
            # CPython fallback
            self.last_activity = int(time.time() * 1000)

    def is_keep_alive_expired(self, factor=1.5):
        """
        Check if keep-alive timeout has expired.

        MQTT spec: Disconnect if no message received within keep_alive * 1.5 seconds.

        Args:
            factor: Multiplier for keep_alive (default 1.5 per MQTT spec)

        Returns:
            bool: True if keep-alive has expired, False otherwise
        """
        if self.keep_alive == 0:
            # Keep-alive disabled
            return False

        # Calculate elapsed time since last activity
        try:
            elapsed_ms = time.ticks_diff(time.ticks_ms(), self.last_activity)
        except AttributeError:
            # CPython fallback
            current_ms = int(time.time() * 1000)
            elapsed_ms = current_ms - self.last_activity

        # Check if exceeded keep-alive threshold
        timeout_ms = self.keep_alive * factor * 1000
        return elapsed_ms > timeout_ms

    def queue_message(self, topic, payload, qos, max_queued=50):
        """
        Queue a message for offline delivery (persistent sessions).
        Uses FIFO eviction when at limit.

        Args:
            topic: Topic name (bytes)
            payload: Message payload (bytes)
            qos: QoS level (0, 1, or 2)
            max_queued: Maximum number of queued messages (default 50)
        """
        if len(self.queued_messages) >= max_queued:
            self.queued_messages.pop(0)  # Remove oldest
        self.queued_messages.append((topic, payload, qos))

    def get_queued_messages(self):
        """
        Get and clear queued messages.

        Returns:
            list: List of (topic, payload, qos) tuples
        """
        messages = self.queued_messages
        self.queued_messages = []
        return messages


class SessionManager:
    """Manages client sessions with lifecycle operations."""

    def __init__(self, sessions, config):
        """
        Initialize session manager.

        Args:
            sessions: Shared dict of client_id -> ClientSession
            config: BrokerConfig instance
        """
        self.sessions = sessions  # shared dict
        self.config = config

    def get_or_create(self, client_id, clean_session):
        """
        Get existing or create new session. Returns (session, session_present).

        Args:
            client_id: Client identifier string
            clean_session: True to create new session, False to reuse

        Returns:
            tuple: (ClientSession, session_present_flag)
        """
        if clean_session:
            session = ClientSession(client_id, clean_session=True)
            return (session, False)
        else:
            if client_id in self.sessions:
                return (self.sessions[client_id], True)
            else:
                session = ClientSession(client_id, clean_session=False)
                return (session, False)

    def remove(self, client_id):
        """
        Remove a session.

        Args:
            client_id: Client identifier to remove
        """
        if client_id in self.sessions:
            del self.sessions[client_id]

    def cleanup_expired(self):
        """
        Remove expired offline sessions.

        Returns:
            int: Number of sessions removed
        """
        # Uses time.ticks_ms() with CPython fallback
        try:
            now = time.ticks_ms()
        except AttributeError:
            now = int(time.time() * 1000)

        expiry_ms = self.config.session_expiry * 1000
        to_remove = []

        for client_id, session in self.sessions.items():
            if not session.connected and not session.clean_session:
                try:
                    elapsed = time.ticks_diff(now, session.last_activity)
                except AttributeError:
                    elapsed = now - session.last_activity
                if elapsed > expiry_ms:
                    to_remove.append(client_id)

        for client_id in to_remove:
            del self.sessions[client_id]

        return len(to_remove)

    def get_connected_count(self):
        """
        Get number of currently connected clients.

        Returns:
            int: Number of connected clients
        """
        count = 0
        for session in self.sessions.values():
            if session.connected:
                count += 1
        return count
