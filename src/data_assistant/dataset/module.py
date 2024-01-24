"""Dataset modules objects."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from .dataset import DatasetAbstract


log = logging.getLogger(__name__)


class Module:
    """Base class for all modules.

    Implements caching and use methods and attributes on the parent dataset object.

    Parameters
    ----------
    dataset
        The parent dataset instance.
    """

    TO_DEFINE_ON_DATASET: Sequence[str] = []
    """Names of attributes to be defined on the parent dataset.

    This helps the user know what attributes and methods they should define on the
    parent dataset.
    """

    def __init__(self, dataset: DatasetAbstract):
        self.dataset = dataset
        self.cache: dict[str, Any] = {}

    def run_on_dataset(self, method: str, *args, **kwargs):
        """Run a method on the parent dataset.

        Parameters
        ----------
        method
            Name of the method to run.
        args, kwargs
            Additional arguments passed to the method.
        """
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
        """Return the value of an attribute on the parent dataset.

        Parameters
        ----------
        attr
            Name of the attribute.
        """
        if hasattr(self.dataset, attr):
            return getattr(self.dataset, attr)
        self.missing_attribute(attr)

    def missing_attribute(self, name: str):
        """Raise an error if attribute/method is undefined on dataset.

        With a hopefully useful message.

        Parameters
        ----------
        name
            Name of the method or attribute.
        """
        classname = self.dataset.__class__.__name__
        msg = f"{classname} has no attribute or method '{name}'."
        if name in self.TO_DEFINE_ON_DATASET:
            msg += f" You must subclass {classname} and define '{name}'."
        raise AttributeError(msg)

    def set_in_cache(self, name: str, value: Any):
        """Add variable to the module cache.

        Parameters
        ----------
        name
            Name of the variable.
        value
            Value to cache.
        """
        self.cache[name] = value

    def clean_cache(self) -> None:
        """Clean the cache of all variables."""
        self.cache = {}

    def get_cached(self, key: str) -> Any:
        """Get value from the cache.

        Parameters
        ----------
        key
            Name of the variable we want the value from.
        """
        # If in cache, easy
        if key in self.cache:
            return self.cache[key]

        name = self.__class__.__name__
        raise KeyError(f"Key '{key}' not found in cache of module '{name}'.")


# Typevar to preserve autocached properties' type.
R = TypeVar("R")


# The `func` argument is typed as Any because technically Callable is contravariant
# and typing it as Module would not allow subclasses.
def autocached(func: Callable[[Any], R]) -> Callable[[Any], R]:
    """Make a property auto-cached.

    If the variable of the same name is in the cache, return its cached value
    immediately. Otherwise run the code of the property and cache the return value.
    """
    name = func.__name__

    @functools.wraps(func)
    def wrapper(self: Any) -> R:
        if name in self.cache:
            return self.get_cached(name)
        value = func(self)
        self.set_in_cache(name, value)
        return value

    return wrapper
