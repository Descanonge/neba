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
import sys
import typing as t
from collections import abc

log = logging.getLogger(__name__)


if t.TYPE_CHECKING:
    from .data_manager import DataManagerBase

    _DB = DataManagerBase
else:
    _DB = object


class Plugin(_DB):
    """Plugin base class."""

    def _init_plugin(self) -> None:
        """Initialize the plugin.

        Because there can be any number of plugins in a dataset parent classes, only
        the first ``__init__`` method found in the mro is run.

        This method however, is run for all plugins that are parent classes. (Not
        all classes in mro, so make sure to propagate the call to the plugin
        parent using ``super()._init_plugin()``).

        By default, does nothing.
        """
        pass


class CachePlugin(Plugin):
    _CACHE_NAME: str

    def _init_plugin(self) -> None:
        name = self._CACHE_NAME
        setattr(self, name, Cache(name))

        def callback(dm: CachePlugin, **kwargs):
            getattr(dm, name).clean()

        self._reset_callbacks[f"void_cache[{name}]"] = callback


class Cache:
    """Cache values.

    Values are simply stored in a dictionnary (:attr:`data`). But the cache should
    be accessed via :meth:`get` or modified with :meth:`set`.

    Multiple plugins can have use of a cache, they then have to share the same cache.
    There are no specific safeties on the name of keys. A plugin could erase or replace
    keys from another plugin. Automatically separating caches from different plugins
    is difficult, even with introspection (at runtime, all methods are bound to the
    same DataManager object!).

    There is currently no proposed solution other than hard-coded keys so that they are
    attached to their plugin, using the plugin class name for instance. This is done
    automatically when using the :func:`autocached` decorator on properties. This
    automatically use the key ``{plugin class name}::{property name}``.
    """

    def __init__(self, name: str = "") -> None:
        """Create a cache if not already created by another plugin."""
        self.name = name
        self.data: dict[str, t.Any] = {}
        """Cache dictionnary."""

    def __str__(self) -> str:
        return str(self.data)

    def __repr__(self) -> str:
        return repr(self.data)

    def clean(self) -> None:
        """Clean the cache of all variables."""
        self.data.clear()

    def set(self, key: str, value: t.Any):
        """Add value to the plugin cache."""
        self.data[key] = value

    def __contains__(self, key: str) -> bool:
        """Check if key is cached."""
        return key in self.data

    def _key_error(self, key: str):
        """Raise slightly more informative message on cache miss."""
        raise KeyError(f"Key '{key}' not found in cache '{self.name}'.")

    def get(self, key: str) -> t.Any:
        """Get value from the cache."""
        if key in self.data:
            return self.data[key]
        self._key_error(key)

    def pop(self, key: str) -> t.Any:
        """Remove key from the cache and return its value."""
        if key in self.data:
            return self.data.pop(key)
        self._key_error(key)


# Typevar to preserve autocached properties' type.
R = t.TypeVar("R")


# The `func` argument is typed as Any because technically Callable is contravariant
# and typing it as Plugin would not allow subclasses.
def autocached(
    func: abc.Callable[[t.Any], R], cache_name: str | None = None
) -> abc.Callable[[t.Any], R]:
    """Make a property auto-cached.

    If the variable of the same name is in the cache, return its cached value
    immediately. Otherwise run the code of the property and cache the return value.
    """
    if cache_name is None:
        frame = sys._getframe(1)
        cache_name = frame.f_locals["_CACHE_NAME"]

    name = func.__name__

    @functools.wraps(func)
    def wrapper(self: t.Any) -> R:
        cache = getattr(self, cache_name)
        if name in cache:
            return cache.get(name)
        value = func(self)
        cache.set(name, value)
        return value

    return wrapper
