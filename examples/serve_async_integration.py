"""
Async Integration Example
==========================

Using BeehiveBrokerSimple.serve_async() to run the broker alongside other async tasks.

This example demonstrates:
- Non-blocking broker startup with serve_async()
- Running broker alongside custom async tasks
- Periodic internal publish from broker
- Combining MQTT broker with application logic

Hardware: ESP32, ESP8266, or any MicroPython-capable board
Memory: ~45KB RAM minimum

Test commands:
    mosquitto_sub -h <ip> -t 'status/#' -v
    mosquitto_sub -h <ip> -t 'sensor/#' -v
"""

from beehivemqtt import BeehiveBrokerSimple

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio


# Create broker
broker = BeehiveBrokerSimple(
    port=1883,
    max_clients=10,
    log_level='INFO'
)


async def sensor_readings():
    """Simulate periodic sensor readings published by broker itself."""
    counter = 0
    while True:
        await asyncio.sleep(5)
        counter += 1
        # Publish sensor data from broker (internal publish)
        broker.publish('sensor/internal/counter', str(counter), qos=0, retain=True)
        print('[Sensor] Published counter: %d' % counter)


async def heartbeat():
    """Periodic heartbeat task."""
    while True:
        await asyncio.sleep(10)
        broker.publish('status/heartbeat', 'alive', qos=0, retain=True)
        print('[Heartbeat] alive')


async def main():
    """Main application combining broker with custom tasks."""
    print('[App] Starting async broker with integration tasks...')
    print('[App] Broker on port 1883')
    print('[App] Sensor readings every 5s -> sensor/internal/counter')
    print('[App] Heartbeat every 10s -> status/heartbeat')
    print('[App] Press Ctrl+C to stop')

    # Start all tasks concurrently
    await asyncio.gather(
        broker.serve_async(),
        sensor_readings(),
        heartbeat()
    )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('[App] Stopped by user')
