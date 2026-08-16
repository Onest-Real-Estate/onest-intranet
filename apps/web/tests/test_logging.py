import logging

from django.conf import settings


def test_apps_logger_is_configured():
    logger = logging.getLogger("apps")
    assert logger.handlers, "the 'apps' logger should have console handlers"
    assert logger.level == logging.getLevelName(settings.LOG_LEVEL)
    assert logger.propagate is False


def test_root_logger_has_console_handler():
    root = logging.getLogger()
    assert any(
        handler.__class__.__name__ == "StreamHandler" for handler in root.handlers
    ), "the root logger should write to the console"


def test_logging_config_defines_expected_handlers():
    assert settings.LOGGING["version"] == 1
    assert "console" in settings.LOGGING["handlers"]
    assert "apps" in settings.LOGGING["loggers"]
