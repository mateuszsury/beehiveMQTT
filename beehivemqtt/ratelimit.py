"""
Rate limiter interceptor for BeehiveMQTT.

Token-bucket rate limiter per client. Integrates as a message interceptor.
MicroPython-compatible with __slots__ and ticks_ms fallback.
"""

import time

# Time functions with CPython fallback
try:
    _ticks_ms = time.ticks_ms
    _ticks_diff = time.ticks_diff
except AttributeError:
    def _ticks_ms():
        return int(time.time() * 1000)

    def _ticks_diff(new, old):
        return new - old


class RateLimiter:
    """Token-bucket rate limiter per client.

    Usage as interceptor:
        limiter = RateLimiter(max_rate=10, window_seconds=1)
        broker.interceptor(limiter)

    Args:
        max_rate: Maximum messages per window (default 10)
        window_seconds: Window size in seconds (default 1)
    """
    __slots__ = ('max_rate', 'window_ms', '_buckets')

    def __init__(self, max_rate=10, window_seconds=1):
        self.max_rate = max_rate
        self.window_ms = window_seconds * 1000
        self._buckets = {}  # client_id -> (tokens, last_refill_ms)

    def __call__(self, ctx):
        """Interceptor interface. Drops message if rate exceeded."""
        client_id = ctx.sender_id
        if client_id is None:
            return  # Broker-internal publishes are not rate-limited

        now = _ticks_ms()
        bucket = self._buckets.get(client_id)

        if bucket is None:
            # First message from this client
            self._buckets[client_id] = (self.max_rate - 1, now)
            return

        tokens, last_refill = bucket
        elapsed = _ticks_diff(now, last_refill)

        if elapsed >= self.window_ms:
            # Refill bucket
            tokens = self.max_rate - 1
            self._buckets[client_id] = (tokens, now)
            return

        if tokens <= 0:
            ctx.drop()
            return

        self._buckets[client_id] = (tokens - 1, last_refill)

    def cleanup_client(self, client_id):
        """Remove bucket for disconnected client."""
        if client_id in self._buckets:
            del self._buckets[client_id]
