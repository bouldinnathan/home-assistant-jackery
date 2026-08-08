"""Pytest configuration: enables the pytest-homeassistant-custom-component harness."""

import os

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def hass_config_dir() -> str:
    """Point the HA test harness at this repo's custom_components, not the plugin's own."""
    return os.path.join(os.path.dirname(__file__), "testing_config")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let every test load custom_components/jackery through the real loader."""
    yield
