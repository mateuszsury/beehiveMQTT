"""
Sensor Mesh with ESP32 Access Point Example
=============================================

ESP32 running as WiFi AP + MQTT broker for a local sensor mesh network.

This example demonstrates:
- ESP32 as WiFi Access Point (no external router needed)
- MQTT broker on the AP for sensor nodes
- Authentication for sensor nodes
- Message hooks for sensor data processing
- Self-contained IoT mesh network

Hardware: ESP32 with WiFi
Memory: ~50KB RAM minimum

Network topology:
    ESP32 AP (192.168.4.1)
      |-- Sensor Node 1 (temperature)
      |-- Sensor Node 2 (humidity)
      |-- Sensor Node 3 (motion)

Sensor nodes connect to the AP WiFi and publish to MQTT broker at 192.168.4.1:1883.

NOTE: This example requires MicroPython on ESP32 with network module.
      The WiFi AP setup code will not work on CPython.
"""

from beehivemqtt import MQTTBroker, BrokerConfig, DictAuthProvider

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio


def setup_ap():
    """Configure ESP32 as WiFi Access Point."""
    try:
        import network
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(
            essid='SensorMesh',
            password='mesh12345',
            authmode=3  # WPA2
        )

        # Wait for AP to be active
        while not ap.active():
            pass

        print('[AP] WiFi Access Point active')
        print('[AP] SSID: SensorMesh')
        print('[AP] IP: %s' % ap.ifconfig()[0])
        return ap
    except ImportError:
        print('[AP] network module not available (running on CPython?)')
        print('[AP] Skipping AP setup, binding to 0.0.0.0')
        return None


# Setup WiFi AP
ap = setup_ap()

# Configure broker for constrained environment
config = BrokerConfig(
    port=1883,
    bind_addr='0.0.0.0',
    max_clients=8,
    max_subscriptions_per_client=5,
    max_payload_size=512,
    max_packet_size=1024,
    max_queued_messages=20,
    max_inflight=3,
    max_retained_messages=30,
    gc_collect_interval=20,
    allow_anonymous=False,
    log_level='INFO'
)

# Authenticate sensor nodes
auth = DictAuthProvider({
    'temp_sensor': 'sensor_key_1',
    'humidity_sensor': 'sensor_key_2',
    'motion_sensor': 'sensor_key_3',
    'gateway': 'gateway_key',
})

# Create broker
broker = MQTTBroker(config=config, auth=auth)

# Sensor data aggregation
sensor_data = {}


@broker.on_connect
def handle_connect(client_id, username, will_topic):
    print('[Mesh] Sensor joined: %s' % client_id)


@broker.on_publish
def handle_publish(client_id, topic, payload, qos, retain):
    topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
    payload_str = payload.decode('utf-8') if isinstance(payload, bytes) else str(payload)

    # Store latest sensor reading
    sensor_data[topic_str] = payload_str
    print('[Mesh] %s: %s = %s' % (client_id, topic_str, payload_str))


@broker.on_disconnect
def handle_disconnect(client_id, graceful):
    status = 'clean' if graceful else 'lost'
    print('[Mesh] Sensor left: %s (%s)' % (client_id, status))


async def status_publisher():
    """Publish mesh status periodically."""
    while True:
        await asyncio.sleep(30)
        count = len(broker.get_clients())
        summary = 'nodes=%d readings=%d' % (count, len(sensor_data))
        await broker.publish(b'mesh/status', summary.encode('utf-8'), qos=0, retain=True)
        print('[Mesh] Status: %s' % summary)


async def main():
    print('[Mesh] Starting Sensor Mesh Broker...')
    print('[Mesh] Port: 1883, Max nodes: 8')
    print('[Mesh] Authenticated nodes: temp, humidity, motion, gateway')

    broker_task = asyncio.create_task(broker.serve())
    status_task = asyncio.create_task(status_publisher())

    await asyncio.gather(broker_task, status_task)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('[Mesh] Stopped by user')
