#!/usr/bin/env python3

import os

import pytest
from hypothesis import HealthCheck, Verbosity, settings

settings.register_profile(
    "ci", max_examples=1000, suppress_health_check=[HealthCheck.too_slow]
)
settings.register_profile("dev", max_examples=50)
settings.register_profile("debug", max_examples=5, verbosity=Verbosity.verbose)

settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "debug").lower())


def pytest_configure(config: pytest.Config):
    config.addinivalue_line("markers", "todo")


todo = pytest.mark.todo
