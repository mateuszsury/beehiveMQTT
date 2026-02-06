"""
Basic MQTT Broker Example
==========================

Minimal MQTT broker running on ESP32 with default settings.

This example demonstrates:
- Starting a broker in 3 lines of code
- Default configuration (port 1883, anonymous access)
- Accepting all client connections
- Handling all MQTT operations (pub/sub/retain/QoS)

Hardware: ESP32, ESP8266, or any MicroPython-capable board
Memory: ~40KB RAM minimum
"""

from beehivemqtt import BeehiveBrokerSimple

# Create and start broker in one line
broker = BeehiveBrokerSimple(port=1883)

# Run broker (blocking - handles Ctrl+C gracefully)
print('[BeehiveMQTT] Starting basic broker on port 1883...')
print('[BeehiveMQTT] Press Ctrl+C to stop')
broker.run()
