"""
BeehiveMQTT - Native MQTT 3.1.1 Broker for MicroPython

Setup script for optional installation via pip (primarily for CPython development/testing)
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='beehivemqtt',
    version='1.0.0',
    author='mateuszsury',
    description='Native MQTT 3.1.1 broker for MicroPython and CPython',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/mateuszsury/BeehiveMQTT',
    project_urls={
        'Bug Tracker': 'https://github.com/mateuszsury/BeehiveMQTT/issues',
        'Documentation': 'https://github.com/mateuszsury/BeehiveMQTT/blob/main/docs/api.md',
        'Source Code': 'https://github.com/mateuszsury/BeehiveMQTT',
    },
    packages=find_packages(),
    python_requires='>=3.7',
    install_requires=[
        # No dependencies for MicroPython compatibility
        # Optional: Add CPython-specific deps for testing
    ],
    extras_require={
        'dev': [
            'pytest>=6.0',
            'pytest-asyncio>=0.18.0',
            'ruff>=0.1.0',
        ],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Embedded Systems',
        'Topic :: System :: Networking',
        'Topic :: Communications',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: MicroPython',
        'Operating System :: OS Independent',
        'Environment :: No Input/Output (Daemon)',
        'Framework :: AsyncIO',
    ],
    keywords='mqtt broker micropython esp32 rp2040 iot embedded asyncio',
    license='Apache-2.0',
    platforms='any',
)
