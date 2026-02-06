"""
ESP32 IoT Gateway Example
=========================

Complete IoT gateway that connects to WiFi and runs an MQTT broker.
Simulates temperature sensors publishing data periodically.

This example demonstrates:
- WiFi connection setup
- Running MQTT broker on ESP32
- Simulating IoT sensor devices
- Publishing sensor data to broker
- Real-world embedded deployment pattern

Hardware: ESP32 with WiFi
Memory: ~60KB RAM minimum

Pin configuration: None needed for this software-only example
"""

try:
    import network
    import machine
except ImportError:
    # Fallback for non-MicroPython (testing on PC)
    network = None
    machine = None

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

from beehivemqtt import MQTTBroker, BrokerConfig
import time


# WiFi credentials - CHANGE THESE
WIFI_SSID = 'your-wifi-ssid'
WIFI_PASSWORD = 'your-wifi-password'

# Broker settings
BROKER_PORT = 1883


def connect_wifi(ssid, password, timeout=20):
    """Connect to WiFi network (ESP32/ESP8266 only)."""
    if network is None:
        print('[WiFi] Network module not available (not on ESP32?)')
        return None

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print('[WiFi] Already connected')
        print('[WiFi] IP address: %s' % wlan.ifconfig()[0])
        return wlan.ifconfig()[0]

    print('[WiFi] Connecting to %s...' % ssid)
    wlan.connect(ssid, password)

    # Wait for connection
    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout:
            print('[WiFi] Connection timeout')
            return None
        time.sleep(0.5)

    ip = wlan.ifconfig()[0]
    print('[WiFi] Connected! IP address: %s' % ip)
    return ip


async def sensor_simulator(broker, sensor_id, topic, interval=10):
    """Simulate a sensor publishing data periodically."""
    import random

    count = 0
    while True:
        await asyncio.sleep(interval)

        # Generate fake sensor reading
        if 'temp' in topic:
            value = 20.0 + random.random() * 10.0  # 20-30 degrees
            unit = 'C'
        elif 'humidity' in topic:
            value = 40.0 + random.random() * 40.0  # 40-80%
            unit = '%'
        else:
            value = random.random() * 100.0
            unit = ''

        # Format message
        payload = '{"sensor":"%s","value":%.2f,"unit":"%s","count":%d}' % (
            sensor_id, value, unit, count
        )

        # Publish to broker
        full_topic = 'sensor/%s' % topic
        print('[SENSOR] Publishing: %s = %.2f%s' % (full_topic, value, unit))
        await broker.publish(full_topic, payload.encode('utf-8'), qos=1, retain=True)

        count += 1


async def main():
    """Main gateway application."""
    print('[IoT Gateway] Starting...')

    # Connect to WiFi if on ESP32
    ip = connect_wifi(WIFI_SSID, WIFI_PASSWORD)

    if ip:
        print('[IoT Gateway] MQTT broker will be available at: %s:%d' % (ip, BROKER_PORT))
    else:
        print('[IoT Gateway] Running without WiFi (localhost only)')

    # Create broker configuration
    config = BrokerConfig(
        port=BROKER_PORT,
        max_clients=10,
        allow_anonymous=True,
        log_level='INFO'
    )

    # Create broker
    broker = MQTTBroker(config=config)

    # Add connection logging
    @broker.on_connect
    def handle_connect(client_id, username, will_topic):
        print('[Gateway] Client connected: %s' % client_id)

    @broker.on_publish
    def handle_publish(client_id, topic, payload, qos, retain):
        topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
        print('[Gateway] Message received on %s' % topic_str)

    # Start broker server task
    broker_task = asyncio.create_task(broker.serve())

    # Wait for broker to initialize
    await asyncio.sleep(2)

    # Start simulated sensors
    sensor1 = asyncio.create_task(
        sensor_simulator(broker, 'temp_01', 'temperature', interval=15)
    )
    sensor2 = asyncio.create_task(
        sensor_simulator(broker, 'humid_01', 'humidity', interval=20)
    )

    print('[IoT Gateway] Simulating 2 sensors (temperature, humidity)')
    print('[IoT Gateway] Press Ctrl+C to stop')

    # Run forever
    await asyncio.gather(broker_task, sensor1, sensor2)


# Run gateway
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('[IoT Gateway] Stopped by user')
