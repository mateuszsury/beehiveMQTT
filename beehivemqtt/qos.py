"""
QoS state machine for MQTT 3.1.1 broker.

Manages QoS 1 and QoS 2 message flows:
- QoS 1: PUBLISH -> PUBACK
- QoS 2 inbound: PUBLISH -> PUBREC -> PUBREL -> PUBCOMP
- QoS 2 outbound: PUBLISH -> PUBREC -> PUBREL -> PUBCOMP
"""

import time
from .packet import build_publish, build_pubrel

# Time functions with CPython fallback
try:
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
except AttributeError:
    # CPython fallback
    def ticks_ms():
        return int(time.time() * 1000)

    def ticks_diff(new, old):
        return new - old


class QoS1Outbound:
    """Track outbound QoS 1 message awaiting PUBACK."""
    __slots__ = ('packet_id', 'topic', 'payload', 'qos', 'retry_count', 'timestamp')

    def __init__(self, packet_id, topic, payload, qos):
        self.packet_id = packet_id
        self.topic = topic
        self.payload = payload
        self.qos = qos
        self.retry_count = 0
        self.timestamp = 0  # Set to ticks_ms() when tracking starts


class QoS2Inbound:
    """Track inbound QoS 2 message (broker sent PUBREC, awaiting PUBREL)."""
    __slots__ = ('packet_id', 'topic', 'payload', 'retain', 'state', 'timestamp')

    PUBREC_SENT = 0     # Waiting for PUBREL
    PUBCOMP_SENT = 1    # Completed

    def __init__(self, packet_id, topic, payload, retain):
        self.packet_id = packet_id
        self.topic = topic
        self.payload = payload
        self.retain = retain
        self.state = QoS2Inbound.PUBREC_SENT
        self.timestamp = 0


class QoS2Outbound:
    """Track outbound QoS 2 message sent to subscriber."""
    __slots__ = ('packet_id', 'topic', 'payload', 'state', 'retry_count', 'timestamp')

    AWAITING_PUBREC = 0
    AWAITING_PUBCOMP = 1
    COMPLETE = 2

    def __init__(self, packet_id, topic, payload):
        self.packet_id = packet_id
        self.topic = topic
        self.payload = payload
        self.state = QoS2Outbound.AWAITING_PUBREC
        self.retry_count = 0
        self.timestamp = 0


class QoSManager:
    """Manages all QoS flows for client sessions."""
    __slots__ = ('config',)

    def __init__(self, config):
        """
        Args:
            config: BrokerConfig with qos_retry_interval, qos_max_retries, max_inflight
        """
        self.config = config

    def track_outbound_qos1(self, session, packet_id, topic, payload, qos):
        """Track outbound QoS 1 PUBLISH awaiting PUBACK."""
        entry = QoS1Outbound(packet_id, topic, payload, qos)
        entry.timestamp = ticks_ms()
        session.pending_qos1[packet_id] = entry
        return entry

    def handle_puback(self, session, packet_id):
        """Handle PUBACK - remove QoS 1 entry."""
        if packet_id in session.pending_qos1:
            del session.pending_qos1[packet_id]
            return True
        return False

    def track_inbound_qos2(self, session, packet_id, topic, payload, retain):
        """Track inbound QoS 2 PUBLISH (broker sent PUBREC, awaiting PUBREL)."""
        entry = QoS2Inbound(packet_id, topic, payload, retain)
        entry.timestamp = ticks_ms()
        session.pending_qos2[packet_id] = entry
        return entry

    def handle_pubrel(self, session, packet_id):
        """Handle PUBREL - mark complete and return message for routing."""
        if packet_id not in session.pending_qos2:
            return None

        entry = session.pending_qos2[packet_id]
        entry.state = QoS2Inbound.PUBCOMP_SENT

        # Return message data for routing, but keep entry until PUBCOMP sent
        return (entry.topic, entry.payload, entry.retain)

    def track_outbound_qos2(self, session, packet_id, topic, payload):
        """Track outbound QoS 2 PUBLISH awaiting PUBREC."""
        entry = QoS2Outbound(packet_id, topic, payload)
        entry.timestamp = ticks_ms()
        session.pending_qos2_out[packet_id] = entry
        return entry

    def handle_pubrec(self, session, packet_id):
        """Handle PUBREC - transition QoS 2 to awaiting PUBCOMP."""
        if packet_id not in session.pending_qos2_out:
            return False

        entry = session.pending_qos2_out[packet_id]
        if entry.state == QoS2Outbound.AWAITING_PUBREC:
            entry.state = QoS2Outbound.AWAITING_PUBCOMP
            entry.timestamp = ticks_ms()  # Reset for PUBREL retry timing
            return True

        return False

    def handle_pubcomp(self, session, packet_id):
        """Handle PUBCOMP - complete QoS 2 flow."""
        if packet_id in session.pending_qos2_out:
            del session.pending_qos2_out[packet_id]
            return True

        # Also clean up inbound QoS 2 if PUBCOMP_SENT state
        if packet_id in session.pending_qos2:
            del session.pending_qos2[packet_id]
            return True

        return False

    async def retransmit_pending(self, session):
        """Retransmit pending QoS messages that need retry."""
        now = ticks_ms()
        retry_interval_ms = self.config.qos_retry_interval * 1000
        max_retries = self.config.qos_max_retries

        # Retransmit QoS 1
        to_remove = []
        for packet_id, entry in session.pending_qos1.items():
            elapsed = ticks_diff(now, entry.timestamp)

            if elapsed < retry_interval_ms:
                continue

            if entry.retry_count >= max_retries:
                to_remove.append(packet_id)
                continue

            try:
                pkt = build_publish(entry.topic, entry.payload, entry.qos,
                                    dup=True, retain=False, packet_id=packet_id)
                await session.send(pkt)
                entry.retry_count += 1
                entry.timestamp = now
            except Exception:
                pass

        for packet_id in to_remove:
            del session.pending_qos1[packet_id]

        # Retransmit outbound QoS 2
        to_remove = []
        for packet_id, entry in session.pending_qos2_out.items():
            elapsed = ticks_diff(now, entry.timestamp)

            if elapsed < retry_interval_ms:
                continue

            if entry.retry_count >= max_retries:
                to_remove.append(packet_id)
                continue

            try:
                if entry.state == QoS2Outbound.AWAITING_PUBREC:
                    pkt = build_publish(entry.topic, entry.payload, 2,
                                        dup=True, retain=False, packet_id=packet_id)
                    await session.send(pkt)
                elif entry.state == QoS2Outbound.AWAITING_PUBCOMP:
                    pkt = build_pubrel(packet_id)
                    await session.send(pkt)

                entry.retry_count += 1
                entry.timestamp = now
            except Exception:
                pass

        for packet_id in to_remove:
            del session.pending_qos2_out[packet_id]

    def get_inflight_count(self, session):
        """Get total number of inflight QoS messages."""
        return len(session.pending_qos1) + len(session.pending_qos2) + len(session.pending_qos2_out)
