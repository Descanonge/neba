#!/usr/bin/env python3

import os

import pytest
from hypothesis import HealthCheck, Phase, Verbosity, settings

settings.register_profile(
    "ci", max_examples=1000, suppress_health_check=[HealthCheck.too_slow]
)
settings.register_profile("dev", max_examples=50)
settings.register_profile(
    "debug",
    max_examples=5,
    verbosity=Verbosity.verbose,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.target],
)

settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev").lower())


def pytest_configure(config: pytest.Config):
    config.addinivalue_line("markers", "todo")


todo = pytest.mark.todo


def pytest_collection_modifyitems(items):
    module_order = [
        "tests.unit.test_various",
        "tests.unit.test_section",
        "tests.unit.test_traits",
        "tests.unit.test_loaders",
        "tests.unit.test_application",
    ]
    module_mapping = {item: item.module.__name__ for item in items}
    sorted_items = []
    for module in module_order:
        sorted_items_mod = [it for it, mod in module_mapping.items() if mod == module]
        for it in sorted_items_mod:
            module_mapping.pop(it)
        sorted_items += sorted_items_mod
    items[:] = sorted_items
