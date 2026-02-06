"""
MicroPython compatibility shim for running BeehiveMQTT tests on CPython.

This module patches time.ticks_ms, time.ticks_diff, time.ticks_cpu, and gc.mem_*
functions to allow tests to run on CPython with pytest.

Import this module at the top of conftest.py to ensure patches are applied globally.
"""

import time
import gc
import sys


# Patch time module for MicroPython compatibility
if not hasattr(time, 'ticks_ms'):
    def ticks_ms():
        """Simulate MicroPython time.ticks_ms() using time.time()."""
        return int(time.time() * 1000) & 0x3FFFFFFF  # 30-bit counter like MicroPython

    time.ticks_ms = ticks_ms


if not hasattr(time, 'ticks_diff'):
    def ticks_diff(new, old):
        """Simulate MicroPython time.ticks_diff() with wraparound handling."""
        diff = new - old
        # Handle 30-bit wraparound
        if diff > 0x20000000:
            diff -= 0x40000000
        elif diff < -0x20000000:
            diff += 0x40000000
        return diff

    time.ticks_diff = ticks_diff


if not hasattr(time, 'ticks_cpu'):
    def ticks_cpu():
        """Simulate MicroPython time.ticks_cpu()."""
        return int(time.perf_counter() * 1000000) & 0xFFFFFFFF

    time.ticks_cpu = ticks_cpu


# Configurable mock memory values for testing MemoryGuard
_mock_mem_free = 50000
_mock_mem_alloc = 30000


def set_mock_mem_free(value):
    """Set the mock gc.mem_free() return value for tests."""
    global _mock_mem_free
    _mock_mem_free = value


def set_mock_mem_alloc(value):
    """Set the mock gc.mem_alloc() return value for tests."""
    global _mock_mem_alloc
    _mock_mem_alloc = value


# Patch gc module for MicroPython compatibility
if not hasattr(gc, '_original_mem_free'):
    def mem_free():
        """Mock gc.mem_free() - configurable via set_mock_mem_free()."""
        return _mock_mem_free

    gc.mem_free = mem_free


if not hasattr(gc, '_original_mem_alloc'):
    def mem_alloc():
        """Mock gc.mem_alloc() - configurable via set_mock_mem_alloc()."""
        return _mock_mem_alloc

    gc.mem_alloc = mem_alloc


# Ensure asyncio is available (prefer standard library)
try:
    import asyncio
except ImportError:
    import uasyncio as asyncio
    sys.modules['asyncio'] = asyncio


print("[micropython_compat] Patches applied for CPython compatibility")
