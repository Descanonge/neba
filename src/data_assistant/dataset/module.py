from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

log = logging.getLogger(__name__)


if TYPE_CHECKING:
    from .dataset import DatasetBase

    _DB = DatasetBase
else:
    _DB = object


class Module(_DB):
    def _init_module(self) -> None:
        pass


@runtime_checkable
class HasCache(Protocol):
    cache: dict[str, Any]

    def clean_cache(self) -> None:
        """Clean the cache of all variables."""
        self.cache.clear()

    def set_in_cache(self, key: str, value: Any):
        """Add variable to the module cache.

        Parameters
        ----------
        key
            Name of the variable.
        value
            Value to cache.
        """
        self.cache[key] = value

    def get_cached(self, key: str) -> Any:
        """Get value from the cache.

        Parameters
        ----------
        key
            Name of the variable we want the value from.
        """
        return self.cache[key]


class CacheModule(HasCache, Module):
    def _init_module(self) -> None:
        super()._init_module()
        # Multiple modules might have a cache
        # The cache is in common. Dangerous.
        if not hasattr(self, "cache"):
            self.cache: dict[str, Any] = {}

    def get_cached(self, key: str) -> Any:
        """Get value from the cache.

        Parameters
        ----------
        key
            Name of the variable we want the value from.
        """
        if key in self.cache:
            return self.cache[key]

        # More informative error message
        name = self.ID or self.SHORTNAME or self.__class__.__name__
        raise KeyError(f"Key '{key}' not found in cache of dataset '{name}'.")


# Typevar to preserve autocached properties' type.
R = TypeVar("R")


# The `func` argument is typed as Any because technically Callable is contravariant
# and typing it as Module would not allow subclasses.
def autocached(func: Callable[[Any], R]) -> Callable[[Any], R]:
    """Make a property auto-cached.

    If the variable of the same name is in the cache, return its cached value
    immediately. Otherwise run the code of the property and cache the return value.
    """
    name = f"{func.__qualname__}::{func.__name__}"

    @functools.wraps(func)
    def wrapper(self: Any) -> R:
        if name in self.cache:
            return self.get_cached(name)
        value = func(self)
        self.set_in_cache(name, value)
        return value

    return wrapper
