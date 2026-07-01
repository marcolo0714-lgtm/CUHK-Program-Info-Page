import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: slow test that requires network access to CUHK course catalog website",
    )
