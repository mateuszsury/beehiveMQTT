"""Simple API for BeehiveMQTT - start a broker in 3 lines."""

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

from .broker import MQTTBroker
from .config import BrokerConfig


class BeehiveBrokerSimple:
    """Simplified MQTT broker interface.

    Example:
        broker = BeehiveBrokerSimple(port=1883)
        broker.run()  # blocking
    """

    def __init__(self, port=1883, max_clients=10, users=None,
                 on_message=None, on_connect=None, on_disconnect=None,
                 auth=None, log_level='INFO'):
        """Initialize simple broker.

        Args:
            port: TCP port (default 1883)
            max_clients: Maximum concurrent clients (default 10)
            users: Dict of {username: password} for authentication
            on_message: Callback(topic, payload, client_id)
            on_connect: Callback(client_id)
            on_disconnect: Callback(client_id)
            auth: Custom auth provider (overrides users)
            log_level: 'DEBUG', 'INFO', 'WARNING', 'ERROR'
        """
        # Create config
        config = BrokerConfig(port=port, max_clients=max_clients, log_level=log_level)

        # Setup auth if users provided
        auth_provider = auth
        if users and auth_provider is None:
            try:
                from .auth import DictAuthProvider
                auth_provider = DictAuthProvider(users)
            except ImportError:
                pass

        # Create broker
        self._broker = MQTTBroker(config=config, auth=auth_provider)

        # Wire callbacks
        if on_message:
            @self._broker.on_publish
            def _on_msg(client_id, topic, payload, qos, retain):
                on_message(topic, payload, client_id)

        if on_connect:
            @self._broker.on_connect
            def _on_conn(client_id, username, will_topic):
                on_connect(client_id)

        if on_disconnect:
            @self._broker.on_disconnect
            def _on_disc(client_id, graceful):
                on_disconnect(client_id)

    def run(self):
        """Start broker (blocking). Handles KeyboardInterrupt gracefully."""
        try:
            asyncio.run(self._broker.serve())
        except KeyboardInterrupt:
            print('[BeehiveMQTT] Stopped by user')

    async def serve_async(self):
        """Start broker as async task (non-blocking)."""
        await self._broker.serve()

    def publish(self, topic, payload, qos=0, retain=False):
        """Publish a message from broker itself.

        Note: This creates a task, must be called from async context or
        will be scheduled for next event loop iteration.
        """
        if isinstance(topic, str):
            topic = topic.encode('utf-8')
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        asyncio.create_task(self._broker.publish(topic, payload, qos, retain))

    def subscribe(self, topic_filter, callback):
        """Subscribe to messages matching a topic filter.

        Registers an internal on_publish hook that filters by topic.
        The callback receives (topic, payload, client_id).

        Args:
            topic_filter: MQTT topic filter (str), supports +/# wildcards
            callback: Callable(topic, payload, client_id)
        """
        # Store existing hook to chain
        prev_hook = self._broker._on_publish

        def _on_pub(client_id, topic, payload, qos, retain):
            if prev_hook:
                prev_hook(client_id, topic, payload, qos, retain)
            topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
            if _filter_matches_topic(topic_filter, topic_str):
                callback(topic, payload, client_id)

        self._broker._on_publish = _on_pub


def _filter_matches_topic(topic_filter, topic_name):
    """Check if an MQTT topic filter matches a topic name.

    Args:
        topic_filter: str, may contain +/# wildcards
        topic_name: str, concrete topic name

    Returns:
        bool: True if filter matches topic
    """
    f_levels = topic_filter.split('/')
    t_levels = topic_name.split('/')

    fi = 0
    ti = 0
    while fi < len(f_levels) and ti < len(t_levels):
        if f_levels[fi] == '#':
            return True
        if f_levels[fi] == '+' or f_levels[fi] == t_levels[ti]:
            fi += 1
            ti += 1
        else:
            return False
    # '#' at end matches zero remaining levels
    if fi < len(f_levels) and f_levels[fi] == '#' and ti == len(t_levels):
        return True
    return fi == len(f_levels) and ti == len(t_levels)
