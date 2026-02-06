# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in BeehiveMQTT, please report it
by opening a GitHub issue with the "security" label.

For sensitive vulnerabilities, please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Scope

BeehiveMQTT is designed for local IoT networks and edge computing.
It does not support TLS/SSL encryption. For production deployments
requiring encrypted connections, place BeehiveMQTT behind a TLS-terminating
proxy or VPN.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
