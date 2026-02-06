"""
MQTT Broker with Event Hooks Example
=====================================

MQTT broker using MQTTBroker directly with decorators to hook into events.

This example demonstrates:
- @on_connect, @on_publish, @on_disconnect decorators
- Logging all client activity
- Tracking message flow
- Monitoring client connections

Hardware: ESP32, ESP8266, or any MicroPython-capable board
Memory: ~45KB RAM minimum
"""

from beehivemqtt import MQTTBroker, BrokerConfig

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio


# Configure broker
config = BrokerConfig(
    port=1883,
    max_clients=10,
    allow_anonymous=True,
    log_level='INFO'
)

# Create broker
broker = MQTTBroker(config=config)


# Hook: Client connects
@broker.on_connect
def handle_connect(client_id, username, will_topic):
    print('[EVENT] Client connected: %s' % client_id)
    stats = broker.get_stats()
    print('[STATS] Total clients: %d' % stats['clients_connected'])


# Hook: Client publishes message
@broker.on_publish
def handle_publish(client_id, topic, payload, qos, retain):
    # Decode topic and payload for display
    topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
    payload_str = payload.decode('utf-8') if isinstance(payload, bytes) else str(payload)

    # Truncate long payloads for display
    if len(payload_str) > 50:
        payload_str = payload_str[:50] + '...'

    print('[EVENT] Publish: %s -> %s (QoS=%d, retain=%s)' % (
        client_id, topic_str, qos, retain
    ))
    print('        Payload: %s' % payload_str)


# Hook: Client subscribes to topic
@broker.on_subscribe
def handle_subscribe(client_id, topic_filter, requested_qos):
    topic_str = topic_filter.decode('utf-8') if isinstance(topic_filter, bytes) else topic_filter
    print('[EVENT] Subscribe: %s -> %s (QoS=%d)' % (
        client_id, topic_str, requested_qos
    ))
    # Return requested QoS to grant, or 0x80 to reject
    return requested_qos


# Hook: Client unsubscribes from topic
@broker.on_unsubscribe
def handle_unsubscribe(client_id, topic_filter):
    topic_str = topic_filter.decode('utf-8') if isinstance(topic_filter, bytes) else topic_filter
    print('[EVENT] Unsubscribe: %s -> %s' % (client_id, topic_str))


# Hook: Client disconnects
@broker.on_disconnect
def handle_disconnect(client_id, graceful):
    disconnect_type = 'CLEAN' if graceful else 'UNEXPECTED'
    print('[EVENT] Client disconnected: %s (%s)' % (client_id, disconnect_type))
    stats = broker.get_stats()
    print('[STATS] Remaining clients: %d' % stats['clients_connected'])


# Print startup info
print('[BeehiveMQTT] Starting broker with event hooks on port 1883')
print('[BeehiveMQTT] All client events will be logged')
print('[BeehiveMQTT] Press Ctrl+C to stop')

# Run broker
try:
    asyncio.run(broker.serve())
except KeyboardInterrupt:
    print('[BeehiveMQTT] Stopped by user')
