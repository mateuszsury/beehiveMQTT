"""
Message router for BeehiveMQTT - native MQTT 3.1.1 broker for MicroPython/ESP32.

Handles routing of PUBLISH messages to matching subscribers and delivery of
retained messages to new subscribers.
"""

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

from .packet import build_publish


class MessageRouter:
    """
    Routes PUBLISH messages to matching subscribers.

    Coordinates between TopicTree (subscription matching) and ClientSessions
    (message delivery). Handles retained messages and ensures clean message
    routing with no echo back to sender.
    """

    def __init__(self, topic_tree, sessions, config, qos_manager=None,
                 retained_store=None, stats=None):
        """
        Initialize message router.

        Args:
            topic_tree: TopicTree instance for subscription matching
            sessions: dict of client_id -> ClientSession (shared with broker)
            config: BrokerConfig instance with retain_enabled flag
            qos_manager: QoSManager instance for QoS 1/2 tracking (optional)
            retained_store: RetainedStore instance for limit enforcement (optional)
            stats: BrokerStats instance for tracking (optional)
        """
        self.topic_tree = topic_tree
        self.sessions = sessions
        self.config = config
        self.qos_manager = qos_manager
        self.retained_store = retained_store
        self.stats = stats

    async def _send_to_subscriber(self, session, topic, payload, effective_qos):
        """Send a message to a connected subscriber at the given QoS.

        Also checks max_inflight before sending QoS 1/2 messages.
        If inflight limit is reached, queues the message instead.

        Args:
            session: ClientSession to deliver to
            topic: Topic name (bytes)
            payload: Message payload (bytes)
            effective_qos: Effective QoS level (0, 1, or 2)
        """
        if effective_qos == 0:
            pkt = build_publish(topic, payload, qos=0, retain=False)
            await session.send(pkt)
        elif effective_qos == 1:
            # Check max_inflight
            if self.qos_manager and self.qos_manager.get_inflight_count(session) >= self.config.max_inflight:
                session.queue_message(topic, payload, effective_qos, self.config.max_queued_messages)
                return
            pid = session.next_packet_id()
            pkt = build_publish(topic, payload, qos=1, retain=False, packet_id=pid)
            await session.send(pkt)
            if self.qos_manager:
                self.qos_manager.track_outbound_qos1(session, pid, topic, payload, 1)
        elif effective_qos == 2:
            # Check max_inflight
            if self.qos_manager and self.qos_manager.get_inflight_count(session) >= self.config.max_inflight:
                session.queue_message(topic, payload, effective_qos, self.config.max_queued_messages)
                return
            pid = session.next_packet_id()
            pkt = build_publish(topic, payload, qos=2, retain=False, packet_id=pid)
            await session.send(pkt)
            if self.qos_manager:
                self.qos_manager.track_outbound_qos2(session, pid, topic, payload)

        # Track stats
        if self.stats:
            self.stats.publishes_sent += 1
            self.stats.messages_sent += 1

    async def route_publish(self, topic, payload, qos, retain, sender_id=None):
        """
        Route a PUBLISH message to all matching subscribers.

        Args:
            topic: Topic name (bytes)
            payload: Message payload (bytes)
            qos: Requested QoS level (0, 1, or 2)
            retain: Retain flag - if True, store as retained message
            sender_id: Client ID of publisher (to avoid echo), or None for broker
        """
        # Handle retained message storage via RetainedStore (enforces limits)
        if retain and self.config.retain_enabled:
            if self.retained_store:
                if len(payload) == 0:
                    self.retained_store.clear(topic)
                else:
                    self.retained_store.set(topic, payload, qos)
            else:
                # Fallback to direct topic_tree access
                if len(payload) == 0:
                    self.topic_tree.set_retained(topic, b'', 0)
                else:
                    self.topic_tree.set_retained(topic, payload, qos)

        # Find all subscribers matching this topic
        subscribers = self.topic_tree.match(topic)

        # Route to each matching subscriber
        for client_id, granted_qos in subscribers.items():
            # Skip sender to avoid message echo
            if client_id == sender_id:
                continue

            # Calculate effective QoS
            effective_qos = min(qos, granted_qos)

            session = self.sessions.get(client_id)
            if session is None:
                continue

            if session.connected:
                await self._send_to_subscriber(session, topic, payload, effective_qos)
            else:
                # Offline client with persistent session: queue message
                # QoS 0 is fire-and-forget, do not queue
                if not session.clean_session and effective_qos > 0:
                    session.queue_message(topic, payload, effective_qos, self.config.max_queued_messages)

    async def deliver_retained(self, session, topic_filter, granted_qos):
        """
        Deliver retained messages matching a topic filter to a subscriber.

        Called when a client subscribes to a topic filter. Sends all matching
        retained messages with retain flag set to True.

        Args:
            session: ClientSession to deliver to
            topic_filter: Topic filter (bytes or str) that was subscribed to
            granted_qos: QoS level granted for this subscription (0, 1, or 2)
        """
        if not self.config.retain_enabled:
            return

        retained_messages = self.topic_tree.get_retained_matching(topic_filter)

        for topic_bytes, payload, msg_qos in retained_messages:
            effective_qos = min(msg_qos, granted_qos)

            try:
                if effective_qos == 0:
                    packet = build_publish(
                        topic=topic_bytes,
                        payload=payload,
                        qos=0,
                        retain=True,
                        dup=False,
                        packet_id=None
                    )
                    await session.send(packet)
                elif effective_qos == 1:
                    pid = session.next_packet_id()
                    packet = build_publish(
                        topic=topic_bytes,
                        payload=payload,
                        qos=1,
                        retain=True,
                        dup=False,
                        packet_id=pid
                    )
                    await session.send(packet)
                    if self.qos_manager:
                        self.qos_manager.track_outbound_qos1(session, pid, topic_bytes, payload, 1)
                elif effective_qos == 2:
                    pid = session.next_packet_id()
                    packet = build_publish(
                        topic=topic_bytes,
                        payload=payload,
                        qos=2,
                        retain=True,
                        dup=False,
                        packet_id=pid
                    )
                    await session.send(packet)
                    if self.qos_manager:
                        self.qos_manager.track_outbound_qos2(session, pid, topic_bytes, payload)
            except OSError:
                break
            except Exception:
                continue

    async def deliver_queued(self, session):
        """
        Deliver queued messages to a reconnected client.

        Args:
            session: ClientSession that has reconnected
        """
        messages = session.get_queued_messages()
        for topic, payload, qos in messages:
            if qos == 0:
                pkt = build_publish(topic, payload, qos=0, retain=False)
                await session.send(pkt)
            elif qos == 1:
                pid = session.next_packet_id()
                pkt = build_publish(topic, payload, qos=1, retain=False, packet_id=pid)
                await session.send(pkt)
                if self.qos_manager:
                    self.qos_manager.track_outbound_qos1(session, pid, topic, payload, 1)
            elif qos == 2:
                pid = session.next_packet_id()
                pkt = build_publish(topic, payload, qos=2, retain=False, packet_id=pid)
                await session.send(pkt)
                if self.qos_manager:
                    self.qos_manager.track_outbound_qos2(session, pid, topic, payload)
