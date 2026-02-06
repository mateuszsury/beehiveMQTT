"""
MQTT Broker with Authentication Example
========================================

MQTT broker with username/password authentication using DictAuthProvider.

This example demonstrates:
- Dictionary-based authentication
- Multiple user accounts with different passwords
- Rejecting unauthorized connection attempts
- Anonymous access disabled

Hardware: ESP32, ESP8266, or any MicroPython-capable board
Memory: ~45KB RAM minimum

Test with mosquitto_pub:
    mosquitto_pub -h <broker-ip> -t 'test' -m 'hello' -u admin -P secret123
"""

from beehivemqtt import BeehiveBrokerSimple

# Create user accounts dictionary
users = {
    'admin': 'secret123',
    'sensor': 'sensor_pass',
    'dashboard': 'dash_pass'
}

# Create broker with authentication
broker = BeehiveBrokerSimple(
    port=1883,
    users=users,
    log_level='INFO'
)

print('[BeehiveMQTT] Starting authenticated broker on port 1883')
print('[BeehiveMQTT] Valid users: admin, sensor, dashboard')
print('[BeehiveMQTT] Anonymous access: DENIED')
print('[BeehiveMQTT] Press Ctrl+C to stop')

broker.run()
