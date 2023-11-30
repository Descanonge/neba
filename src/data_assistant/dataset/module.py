from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from .dataset import DatasetAbstract


log = logging.getLogger(__name__)


class Module:
    TO_DEFINE_ON_DATASET: Sequence[str] = []

    def __init__(self, dataset: DatasetAbstract):
        self.dataset = dataset
        self.cache: dict[str, Any] = {}

    def run_on_dataset(self, method: str, *args, **kwargs):
        if hasattr(self.dataset, method) and callable(getattr(self.dataset, method)):
            func = getattr(self.dataset, method)

            # We use PARAMS_NAMES instead of allowed_params which contains
            # fixables, which can be missing in some operations
            missing = [
                p for p in self.dataset.PARAMS_NAMES if p not in self.dataset.params
            ]
            if missing:
                log.warning("Possibly missing parameters %s", str(missing))

            return func(*args, **kwargs)

        self.missing_attribute(method)

    def get_attr_dataset(self, attr: str):
        if hasattr(self.dataset, attr):
            return getattr(self.dataset, attr)
        self.missing_attribute(attr)

    def missing_attribute(self, name: str):
        classname = self.dataset.__class__.__name__
        msg = f"{classname} has no attribute or method '{name}'."
        if name in self.TO_DEFINE_ON_DATASET:
            msg += f" You must subclass {classname} and define '{name}'."
        raise AttributeError(msg)

    def clean_cache(self) -> None:
        self.cache = {}

    def get_cached(self, key: str) -> Any:
        # If in cache, easy
        if key in self.cache:
            return self.cache[key]

        raise KeyError(f"Key '{key}' not found in cache.")


R = TypeVar("R")


# The `func` argument is type as Any because technically Callable is contravariant
# and typing it as Module would not allow subclasses.
def autocached(func: Callable[[Any], R]) -> Callable[[Any], R]:
    """Make a property auto-cached.

    If it's in the cache, return this value directly. Otherwise run the
    code of the property and cache the return value.
    """
    name = func.__name__

    @functools.wraps(func)
    def wrapper(self: Any) -> R:
        if name in self.cache:
            value = self.cache[name]
            return self.cache[name]
        value = func(self)
        self.cache[name] = value
        return value

    return wrapper
