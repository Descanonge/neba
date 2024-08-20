"""Definition of base Plugin for the DataManager.

Each plugin is a mixin class that adds functionalities to a DataManager base class,
allowing the user to choose how to deal with various parts of loading/writing data.

Mixins are meant to be independant of each others, but some plugins might need to
exchange information. The minimal case of a plugin managing loading data might want
another plugin to locate the files to load.

To allow this, plugins have access to *at least* the API of :class:`DataManagerAbstract`
that involves some basic plugins. If more inter-dependency is required, one can check
for classes in ``self.__class__.__bases__`` to make sure another plugin is present, or
better yet to create a "third" plugin the depend on other plugin(s), see
:class:`.xarray.XarraySplitWriterPlugin` for a practical example.
"""

from __future__ import annotations

import functools
import logging
import typing as t
from collections import abc

log = logging.getLogger(__name__)


if t.TYPE_CHECKING:
    from .data_manager import DataManagerBase


class Module:
    _attr_name: str

    def __init__(self, dm: DataManagerBase, *args, **kwargs):
        self.dm = dm
        self._init_module()

    def _init_module(self) -> None:
        pass


class CachedModule(Module):
    """Plugin containing a cache."""

    def _init_module(self) -> None:
        self.cache: dict[str, t.Any] = {}

        # Voiding callback
        # we make sure to avoid late-binding by using functools.partial
        def callback(dm, **kwargs) -> None:
            mod = getattr(dm, self._attr_name)
            mod.void_cache()

        key = f"void_cache[{self.__class__.__name__}]"
        self.dm._register_callback(key, callback)

    def void_cache(self) -> None:
        self.cache.clear()


# Typevar to preserve autocached properties' type.
R = t.TypeVar("R")


# The `func` argument is typed as Any because technically Callable is contravariant
# and typing it as Plugin would not allow subclasses.
def get_autocached(
    name: str,
) -> abc.Callable[[abc.Callable[[t.Any], R]], abc.Callable[[t.Any], R]]:
    """Generate decorator to make a property autocached.

    Parameters
    ----------
    name
        Attribute name where the cache is located.
    """

    def decorator(func: abc.Callable[[t.Any], R]) -> abc.Callable[[t.Any], R]:
        """Automatically cache a property."""
        property_name = func.__name__

        @functools.wraps(func)
        def wrap(self: t.Any) -> R:
            cache = getattr(self, name)
            if property_name in cache:
                return cache[property_name]
            result = func(self)
            cache[property_name] = result
            return result

        return wrap

    return decorator
