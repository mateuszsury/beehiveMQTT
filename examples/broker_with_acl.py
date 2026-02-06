"""
MQTT Broker with ACL (Access Control Lists) Example
====================================================

MQTT broker with role-based access control using ACLAuthProvider.
Different users have different permissions based on topic patterns.

This example demonstrates:
- Role-based authentication
- Topic-level publish/subscribe authorization
- Wildcard topic patterns in ACL rules
- Separating sensor and client permissions

Hardware: ESP32, ESP8266, or any MicroPython-capable board
Memory: ~50KB RAM minimum

Roles:
- admin: Full access to all topics (#)
- sensor: Publish only to sensor/# topics
- viewer: Subscribe only to sensor/# topics

Test commands:
    # Admin can publish anywhere
    mosquitto_pub -h <ip> -t 'admin/test' -m 'ok' -u admin -P admin123

    # Sensor can publish to sensor/# but not subscribe
    mosquitto_pub -h <ip> -t 'sensor/temp' -m '25.5' -u temp_sensor -P sensorpass

    # Viewer can subscribe to sensor/# but not publish
    mosquitto_sub -h <ip> -t 'sensor/#' -u monitor -P viewpass
"""

from beehivemqtt import MQTTBroker, BrokerConfig, ACLAuthProvider

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio


# Configure broker
config = BrokerConfig(
    port=1883,
    max_clients=15,
    log_level='INFO'
)

# Create ACL auth provider
auth = ACLAuthProvider()

# Add users with roles
auth.add_user('admin', 'admin123', role='admin')
auth.add_user('temp_sensor', 'sensorpass', role='sensor')
auth.add_user('humidity_sensor', 'sensorpass', role='sensor')
auth.add_user('monitor', 'viewpass', role='viewer')
auth.add_user('dashboard', 'viewpass', role='viewer')

# Define ACL rules
# Admin has full access
auth.add_acl('admin', '#', publish=True, subscribe=True)

# Sensors can publish to sensor/# but cannot subscribe
auth.add_acl('sensor', 'sensor/#', publish=True, subscribe=False)

# Viewers can subscribe to sensor/# but cannot publish
auth.add_acl('viewer', 'sensor/#', publish=False, subscribe=True)

# Create broker
broker = MQTTBroker(config=config, auth=auth)

# Add connection logging hook
@broker.on_connect
def handle_connect(client_id, username, will_topic):
    print('[ACL] Client connected: %s' % client_id)

@broker.on_publish
def handle_publish(client_id, topic, payload, qos, retain):
    topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
    print('[ACL] Publish from %s: %s' % (client_id, topic_str))

print('[BeehiveMQTT] Starting ACL-enabled broker on port 1883')
print('[BeehiveMQTT] Roles configured:')
print('  - admin: Full access to #')
print('  - sensor: Publish to sensor/#')
print('  - viewer: Subscribe to sensor/#')
print('[BeehiveMQTT] Press Ctrl+C to stop')

# Run broker
try:
    asyncio.run(broker.serve())
except KeyboardInterrupt:
    print('[BeehiveMQTT] Stopped by user')
