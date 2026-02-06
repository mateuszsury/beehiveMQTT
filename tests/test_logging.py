"""Tests for beehivemqtt.logging module."""

import pytest
from beehivemqtt.logging import (
    Logger, get_logger, DEBUG, INFO, WARNING, ERROR,
    _loggers, _LEVEL_NAMES, _NAME_LEVELS
)


class TestLoggerConstants:
    """Test logging level constants and mappings."""

    def test_level_ordering(self):
        """Test that level constants have correct ordering."""
        assert DEBUG < INFO < WARNING < ERROR

    def test_level_values(self):
        """Test that level constants have expected integer values."""
        assert DEBUG == 0
        assert INFO == 1
        assert WARNING == 2
        assert ERROR == 3

    def test_level_names_mapping(self):
        """Test _LEVEL_NAMES maps integers to display strings."""
        assert _LEVEL_NAMES[0] == 'DEBUG'
        assert _LEVEL_NAMES[1] == 'INFO'
        assert _LEVEL_NAMES[2] == 'WARN'
        assert _LEVEL_NAMES[3] == 'ERROR'

    def test_name_levels_mapping(self):
        """Test _NAME_LEVELS maps strings to integers."""
        assert _NAME_LEVELS['DEBUG'] == 0
        assert _NAME_LEVELS['INFO'] == 1
        assert _NAME_LEVELS['WARNING'] == 2
        assert _NAME_LEVELS['ERROR'] == 3


class TestLoggerInit:
    """Test Logger initialization."""

    def test_init_with_default_level(self):
        """Test Logger initializes with INFO level by default."""
        logger = Logger('test')

        assert logger.name == 'test'
        assert logger.level == INFO

    def test_init_with_int_level(self):
        """Test Logger initializes with integer level."""
        logger = Logger('test', level=DEBUG)

        assert logger.level == DEBUG

    def test_init_with_error_int_level(self):
        """Test Logger initializes with ERROR integer level."""
        logger = Logger('test', level=ERROR)

        assert logger.level == ERROR

    def test_init_with_string_level_debug(self):
        """Test Logger initializes with string level 'DEBUG'."""
        logger = Logger('test', level='DEBUG')

        assert logger.level == DEBUG

    def test_init_with_string_level_warning(self):
        """Test Logger initializes with string level 'WARNING'."""
        logger = Logger('test', level='WARNING')

        assert logger.level == WARNING

    def test_init_with_string_level_error(self):
        """Test Logger initializes with string level 'ERROR'."""
        logger = Logger('test', level='ERROR')

        assert logger.level == ERROR

    def test_init_with_unknown_string_level_defaults_to_info(self):
        """Test Logger with unknown string level defaults to INFO."""
        logger = Logger('test', level='UNKNOWN')

        assert logger.level == INFO

    def test_uses_slots(self):
        """Test Logger uses __slots__ for memory efficiency."""
        logger = Logger('test')

        assert hasattr(Logger, '__slots__')
        assert 'name' in Logger.__slots__
        assert 'level' in Logger.__slots__

        with pytest.raises(AttributeError):
            logger.extra_attr = 'should fail'


class TestLoggerOutput:
    """Test Logger output formatting and level filtering."""

    def test_info_message_format(self, capsys):
        """Test info message prints with correct format."""
        logger = Logger('broker', level=INFO)

        logger.info('server started')

        captured = capsys.readouterr()
        assert captured.out == '[INFO] broker: server started\n'

    def test_debug_message_format(self, capsys):
        """Test debug message prints with correct format."""
        logger = Logger('broker', level=DEBUG)

        logger.debug('initializing')

        captured = capsys.readouterr()
        assert captured.out == '[DEBUG] broker: initializing\n'

    def test_warning_message_format(self, capsys):
        """Test warning message prints with WARN label."""
        logger = Logger('broker', level=WARNING)

        logger.warning('high memory usage')

        captured = capsys.readouterr()
        assert captured.out == '[WARN] broker: high memory usage\n'

    def test_error_message_format(self, capsys):
        """Test error message prints with correct format."""
        logger = Logger('broker', level=ERROR)

        logger.error('connection failed')

        captured = capsys.readouterr()
        assert captured.out == '[ERROR] broker: connection failed\n'

    def test_message_with_percent_formatting_single_arg(self, capsys):
        """Test message with single % format argument."""
        logger = Logger('broker', level=INFO)

        logger.info('connected to %s', 'localhost')

        captured = capsys.readouterr()
        assert captured.out == '[INFO] broker: connected to localhost\n'

    def test_message_with_percent_formatting_multiple_args(self, capsys):
        """Test message with multiple % format arguments."""
        logger = Logger('broker', level=INFO)

        logger.info('client %s on port %d', 'sensor-01', 1883)

        captured = capsys.readouterr()
        assert captured.out == '[INFO] broker: client sensor-01 on port 1883\n'

    def test_message_with_int_formatting(self, capsys):
        """Test message with integer % format argument."""
        logger = Logger('stats', level=DEBUG)

        logger.debug('messages: %d, bytes: %d', 42, 1024)

        captured = capsys.readouterr()
        assert captured.out == '[DEBUG] stats: messages: 42, bytes: 1024\n'

    def test_message_without_args_no_formatting(self, capsys):
        """Test message without args does not attempt formatting."""
        logger = Logger('test', level=DEBUG)

        # This contains a % but no args, so it should not be formatted
        logger.debug('100% complete')

        captured = capsys.readouterr()
        assert captured.out == '[DEBUG] test: 100% complete\n'


class TestLoggerFiltering:
    """Test Logger level filtering."""

    def test_debug_suppressed_at_info_level(self, capsys):
        """Test debug messages are suppressed when level is INFO."""
        logger = Logger('test', level=INFO)

        logger.debug('this should not appear')

        captured = capsys.readouterr()
        assert captured.out == ''

    def test_info_suppressed_at_warning_level(self, capsys):
        """Test info messages are suppressed when level is WARNING."""
        logger = Logger('test', level=WARNING)

        logger.info('this should not appear')

        captured = capsys.readouterr()
        assert captured.out == ''

    def test_warning_suppressed_at_error_level(self, capsys):
        """Test warning messages are suppressed when level is ERROR."""
        logger = Logger('test', level=ERROR)

        logger.warning('this should not appear')

        captured = capsys.readouterr()
        assert captured.out == ''

    def test_debug_visible_at_debug_level(self, capsys):
        """Test debug messages are visible when level is DEBUG."""
        logger = Logger('test', level=DEBUG)

        logger.debug('visible')

        captured = capsys.readouterr()
        assert 'visible' in captured.out

    def test_error_visible_at_all_levels(self, capsys):
        """Test error messages are visible regardless of level."""
        for level in (DEBUG, INFO, WARNING, ERROR):
            logger = Logger('test', level=level)

            logger.error('always visible')

            captured = capsys.readouterr()
            assert '[ERROR] test: always visible\n' == captured.out

    def test_info_and_above_at_info_level(self, capsys):
        """Test that INFO level allows info, warning, and error."""
        logger = Logger('test', level=INFO)

        logger.debug('no')
        logger.info('yes1')
        logger.warning('yes2')
        logger.error('yes3')

        captured = capsys.readouterr()
        assert 'no' not in captured.out
        assert 'yes1' in captured.out
        assert 'yes2' in captured.out
        assert 'yes3' in captured.out

    def test_same_level_message_is_printed(self, capsys):
        """Test that a message at exactly the logger level is printed."""
        logger = Logger('test', level=WARNING)

        logger.warning('at threshold')

        captured = capsys.readouterr()
        assert 'at threshold' in captured.out


class TestGetLogger:
    """Test get_logger factory function with caching."""

    def setup_method(self):
        """Clear the logger cache before each test."""
        _loggers.clear()

    def test_creates_new_logger(self):
        """Test get_logger creates a new Logger instance."""
        logger = get_logger('mqtt')

        assert isinstance(logger, Logger)
        assert logger.name == 'mqtt'

    def test_default_level_is_info(self):
        """Test get_logger creates logger with INFO level by default."""
        logger = get_logger('mqtt')

        assert logger.level == INFO

    def test_custom_level(self):
        """Test get_logger creates logger with specified level."""
        logger = get_logger('mqtt', level=DEBUG)

        assert logger.level == DEBUG

    def test_returns_cached_instance(self):
        """Test get_logger returns the same instance for the same name."""
        logger1 = get_logger('broker')
        logger2 = get_logger('broker')

        assert logger1 is logger2

    def test_cached_ignores_different_level(self):
        """Test get_logger returns cached instance even with different level."""
        logger1 = get_logger('broker', level=DEBUG)
        logger2 = get_logger('broker', level=ERROR)

        assert logger1 is logger2
        assert logger2.level == DEBUG  # Original level preserved

    def test_different_names_different_instances(self):
        """Test get_logger creates separate instances for different names."""
        logger1 = get_logger('broker')
        logger2 = get_logger('router')

        assert logger1 is not logger2
        assert logger1.name == 'broker'
        assert logger2.name == 'router'

    def test_stored_in_loggers_dict(self):
        """Test get_logger stores the logger in the _loggers dict."""
        logger = get_logger('session')

        assert 'session' in _loggers
        assert _loggers['session'] is logger

    def test_multiple_loggers_cached(self):
        """Test multiple loggers are all cached independently."""
        names = ['broker', 'router', 'session', 'auth']
        loggers = [get_logger(name) for name in names]

        assert len(_loggers) == 4
        for name, logger in zip(names, loggers):
            assert _loggers[name] is logger
