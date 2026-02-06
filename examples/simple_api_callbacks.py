"""
Simple API with Callbacks Example
==================================

Using BeehiveBrokerSimple with on_message, on_connect, on_disconnect callbacks.

This example demonstrates:
- Simple 3-line broker setup
- Message callback for logging incoming publishes
- Connect/disconnect callbacks for client tracking
- Internal subscribe for filtered topic monitoring

Hardware: ESP32, ESP8266, or any MicroPython-capable board
Memory: ~40KB RAM minimum

Test commands:
    mosquitto_pub -h <ip> -t 'sensor/temp' -m '22.5'
    mosquitto_sub -h <ip> -t 'sensor/#'
"""

from beehivemqtt import BeehiveBrokerSimple


# Callbacks
def on_message(topic, payload, client_id):
    topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
    payload_str = payload.decode('utf-8') if isinstance(payload, bytes) else str(payload)
    print('[MSG] %s -> %s = %s' % (client_id, topic_str, payload_str))


def on_connect(client_id):
    print('[CONN] Client connected: %s' % client_id)


def on_disconnect(client_id):
    print('[DISC] Client disconnected: %s' % client_id)


# Create broker with all callbacks
broker = BeehiveBrokerSimple(
    port=1883,
    max_clients=10,
    on_message=on_message,
    on_connect=on_connect,
    on_disconnect=on_disconnect,
    log_level='INFO'
)

# Also subscribe to specific topic for filtered monitoring
alerts = []


def alert_callback(topic, payload, client_id):
    topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
    payload_str = payload.decode('utf-8') if isinstance(payload, bytes) else str(payload)
    alerts.append((topic_str, payload_str))
    print('[ALERT] %s: %s' % (topic_str, payload_str))


broker.subscribe('alert/#', alert_callback)

print('[BeehiveMQTT] Starting Simple API broker on port 1883')
print('[BeehiveMQTT] Callbacks: on_message, on_connect, on_disconnect')
print('[BeehiveMQTT] Subscribed to: alert/#')
print('[BeehiveMQTT] Press Ctrl+C to stop')

# Run (blocking)
broker.run()
