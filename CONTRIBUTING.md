# Contributing to BeehiveMQTT

Thank you for your interest in contributing to BeehiveMQTT! This document provides guidelines for contributing to this native MQTT 3.1.1 broker for MicroPython on ESP32.

## Development Setup

### Clone the Repository

```bash
git clone https://github.com/mateuszsury/beehivemqtt.git
cd beehivemqtt
```

### Create Virtual Environment

```bash
python -m venv .venv
```

Activate the virtual environment:
- Windows: `.venv\Scripts\activate`
- Linux/Mac: `source .venv/bin/activate`

### Install Development Dependencies

```bash
pip install pytest ruff
```

## Code Style Requirements

BeehiveMQTT is designed to run on MicroPython with limited resources. All code must follow these requirements:

### MicroPython Compatibility Rules

1. **Use `__slots__` on all data classes** to minimize memory usage:
   ```python
   class Packet:
       __slots__ = ('type', 'flags', 'payload')

       def __init__(self, type, flags, payload):
           self.type = type
           self.flags = flags
           self.payload = payload
   ```

2. **No f-strings** - Use `%` formatting instead:
   ```python
   # Bad
   msg = f"Client {client_id} connected"

   # Good
   msg = "Client %s connected" % client_id
   msg = "Client %s at %s:%d" % (client_id, host, port)
   ```

3. **No typing imports at runtime** - Type hints must be strings or use `TYPE_CHECKING`:
   ```python
   from typing import TYPE_CHECKING

   if TYPE_CHECKING:
       from typing import Optional, List

   def process(data):  # type: (bytes) -> Optional[str]
       pass
   ```

4. **No match/case or walrus operator** - These features are not available in MicroPython:
   ```python
   # Bad
   match packet_type:
       case 1: handle_connect()
       case 2: handle_connack()

   # Good
   if packet_type == 1:
       handle_connect()
   elif packet_type == 2:
       handle_connack()
   ```

5. **Iterative algorithms** - Avoid deep recursion due to limited stack:
   ```python
   # Bad
   def process_tree(node):
       if node.left:
           process_tree(node.left)
       if node.right:
           process_tree(node.right)

   # Good
   def process_tree(root):
       stack = [root]
       while stack:
           node = stack.pop()
           if node.left:
               stack.append(node.left)
           if node.right:
               stack.append(node.right)
   ```

6. **Use `struct.pack` and `struct.unpack_from` for binary data**:
   ```python
   import struct

   # Encoding
   data = struct.pack('!HB', packet_id, qos)

   # Decoding
   packet_id, qos = struct.unpack_from('!HB', buffer, offset)
   ```

7. **Use `time.ticks_ms()` with CPython fallback**:
   ```python
   try:
       from time import ticks_ms, ticks_diff
   except ImportError:
       from time import time
       ticks_ms = lambda: int(time() * 1000)
       ticks_diff = lambda a, b: a - b
   ```

8. **Use `asyncio` with `uasyncio` fallback**:
   ```python
   try:
       import asyncio
   except ImportError:
       import uasyncio as asyncio
   ```

## Running Tests

Execute the test suite with pytest:

```bash
pytest tests/ -v
```

To run specific tests:

```bash
pytest tests/test_packet.py -v
pytest tests/test_broker.py::test_connect -v
```

## Linting

Check code style with ruff:

```bash
ruff check beehivemqtt/
```

Fix auto-fixable issues:

```bash
ruff check --fix beehivemqtt/
```

## Pull Request Process

1. **Fork the repository** and create a new branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code style requirements above.

3. **Write or update tests** for your changes.

4. **Run tests and linting** to ensure everything passes:
   ```bash
   pytest tests/ -v
   ruff check beehivemqtt/
   ```

5. **Commit your changes** using the commit message format below.

6. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Open a Pull Request** with:
   - Clear description of the changes
   - Reference to any related issues
   - Test results demonstrating the changes work

### Commit Message Format

Use the following format for commit messages:

```
type(scope): brief description

Optional longer description explaining the change in detail.
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Adding or updating tests
- `refactor`: Code refactoring without functionality changes
- `perf`: Performance improvements
- `chore`: Maintenance tasks

Examples:
```
feat(broker): add support for retain message handling
fix(packet): correct variable header parsing for PUBLISH
docs(readme): update installation instructions
test(session): add tests for session expiry
```

## Reporting Bugs

When reporting bugs, please include:

1. **Description** - Clear description of the issue
2. **Environment** - MicroPython version, ESP32 board type, memory available
3. **Reproduction steps** - Minimal code to reproduce the issue
4. **Expected behavior** - What you expected to happen
5. **Actual behavior** - What actually happened
6. **Logs** - Any relevant error messages or logs
7. **Code sample** - Minimal code that demonstrates the problem

Example:
```
**Environment:**
- MicroPython: v1.22.0
- Board: ESP32-WROOM-32
- Free memory: 45KB

**Steps to reproduce:**
1. Start broker with default config
2. Connect client with QoS 2
3. Publish message to topic

**Expected:** Message delivered with QoS 2
**Actual:** Connection drops with error "Memory allocation failed"
```

## Questions or Need Help?

If you have questions or need help contributing, please open an issue with the `question` label. We're here to help!

Thank you for contributing to BeehiveMQTT!
