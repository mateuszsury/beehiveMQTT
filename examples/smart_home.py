"""
Smart Home Hub Example
======================

Smart home MQTT hub with authentication, logging, and message filtering.

This example demonstrates:
- Authentication for device access control
- Event hooks for activity logging
- Message interceptors for content filtering
- Topic-based device organization
- Real-world smart home deployment pattern

Hardware: ESP32
Memory: ~50KB RAM minimum

Topics:
- home/light/+      - Light control (on/off/brightness)
- home/sensor/+     - Sensor readings (temperature, motion, door)
- home/thermostat/+ - Climate control
- admin/#           - Admin/configuration topics (filtered)
"""

from beehivemqtt import MQTTBroker, BrokerConfig, DictAuthProvider

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio


# Create broker configuration
config = BrokerConfig(
    port=1883,
    max_clients=20,
    max_subscriptions_per_client=30,
    allow_anonymous=False,  # Require authentication
    log_level='INFO'
)

# Set up authentication
auth = DictAuthProvider({
    'homeassistant': 'ha_secret_2024',
    'light_controller': 'light_pass',
    'temp_sensor': 'sensor_pass',
    'admin': 'admin_secure_pass'
})

# Create broker
broker = MQTTBroker(config=config, auth=auth)


# Connection event logging
@broker.on_connect
def handle_connect(client_id, username, will_topic):
    print('[SmartHome] Device connected: %s' % client_id)

    # Track connected devices
    clients = broker.get_clients()
    device_count = len([c for c in clients if c['connected']])
    print('[SmartHome] Total devices online: %d' % device_count)


# Publish event logging with smart home context
@broker.on_publish
def handle_publish(client_id, topic, payload, qos, retain):
    topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
    payload_str = payload.decode('utf-8') if isinstance(payload, bytes) else str(payload)

    # Categorize by topic
    if topic_str.startswith('home/light/'):
        device = topic_str.split('/')[-1]
        print('[SmartHome] Light update: %s = %s' % (device, payload_str))

    elif topic_str.startswith('home/sensor/'):
        device = topic_str.split('/')[-1]
        print('[SmartHome] Sensor reading: %s = %s' % (device, payload_str))

    elif topic_str.startswith('home/thermostat/'):
        device = topic_str.split('/')[-1]
        print('[SmartHome] Thermostat: %s = %s' % (device, payload_str))

    else:
        print('[SmartHome] Message: %s' % topic_str)


# Disconnect logging
@broker.on_disconnect
def handle_disconnect(client_id, graceful):
    status = 'clean' if graceful else 'unexpected'
    print('[SmartHome] Device disconnected: %s (%s)' % (client_id, status))


# Message interceptor: Filter sensitive topics
@broker.interceptor
def filter_admin_topics(ctx):
    """Block unauthorized access to admin topics."""
    topic_str = ctx.topic.decode('utf-8') if isinstance(ctx.topic, bytes) else ctx.topic

    # Only admin clients can publish to admin/* topics
    if topic_str.startswith('admin/') and ctx.sender_id != 'admin':
        print('[SmartHome] Blocked unauthorized admin publish from %s' % ctx.sender_id)
        ctx.drop()


# Message interceptor: Log all commands
@broker.interceptor
def log_commands(ctx):
    """Log all control commands (non-sensor topics)."""
    topic_str = ctx.topic.decode('utf-8') if isinstance(ctx.topic, bytes) else ctx.topic

    # Log commands (not sensor readings)
    if 'sensor' not in topic_str:
        payload_str = ctx.payload.decode('utf-8') if isinstance(ctx.payload, bytes) else str(ctx.payload)
        if len(payload_str) > 30:
            payload_str = payload_str[:30] + '...'
        print('[SmartHome] Command: %s = %s' % (topic_str, payload_str))


# Message interceptor: Content filter for safety
@broker.interceptor
def content_filter(ctx):
    """Drop messages with potentially dangerous content."""
    # Check payload for dangerous keywords
    if isinstance(ctx.payload, bytes):
        payload_lower = ctx.payload.lower()
    else:
        payload_lower = str(ctx.payload).lower()

    # Block messages containing script injection attempts
    dangerous = [b'<script', b'javascript:', b'eval(', b'system(']
    for keyword in dangerous:
        if keyword in payload_lower:
            print('[SmartHome] Blocked dangerous content from %s' % ctx.sender_id)
            ctx.drop()
            return


async def periodic_stats():
    """Print broker statistics every 60 seconds."""
    while True:
        await asyncio.sleep(60)

        stats = broker.get_stats()
        print('[SmartHome] === Hourly Statistics ===')
        print('  Uptime: %d seconds' % stats['uptime'])
        print('  Devices connected: %d' % stats['clients_connected'])
        print('  Messages received: %d' % stats['messages_received'])
        print('  Messages sent: %d' % stats['messages_sent'])
        print('  Retained messages: %d' % stats['retained_messages'])


async def main():
    """Main smart home hub application."""
    print('[SmartHome] Starting Smart Home Hub...')
    print('[SmartHome] Broker port: 1883')
    print('[SmartHome] Authentication: ENABLED')
    print('[SmartHome] Message filtering: ENABLED')
    print('[SmartHome] Press Ctrl+C to stop')

    # Start broker
    broker_task = asyncio.create_task(broker.serve())

    # Start stats task
    stats_task = asyncio.create_task(periodic_stats())

    # Run both tasks
    await asyncio.gather(broker_task, stats_task)


# Run smart home hub
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('[SmartHome] Shutting down...')
