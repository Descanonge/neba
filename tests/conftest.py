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
        "tests.config.test_various",
        "tests.config.test_section",
        "tests.config.test_traits",
        "tests.config.test_loaders",
        "tests.config.test_application",
        "tests.datasets.test_dataset",
        "tests.datasets.test_params",
    ]
    module_mapping = {item: item.module.__name__ for item in items}
    sorted_items = []
    for module in module_order:
        sorted_items_mod = [it for it, mod in module_mapping.items() if mod == module]
        for it in sorted_items_mod:
            module_mapping.pop(it)
        sorted_items += sorted_items_mod
    # add items that were not found
    sorted_items += [it for it in items if it not in sorted_items]
    items[:] = sorted_items
