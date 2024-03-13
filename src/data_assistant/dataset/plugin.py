"""Plugin for the DataManager.

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
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

log = logging.getLogger(__name__)


if TYPE_CHECKING:
    from .dataset import DataManagerBase

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
    """Cache values.

    Values are simply stored in a dictionnary (:attr:`cache`). But the cache should
    be accessed via :meth:`get_cached` or modified with :meth:`set_in_cache`.

    Multiple plugins can have use of a cache, they then have to share the same cache.
    There are no specific safeties on the name of keys. A plugin could erase or replace
    keys from another plugin. Automatically separating caches from different plugins
    is difficult, even with introspection (at runtime, all methods are bound to the
    same DataManager object!).

    There is currently no proposed solution other than hard-code keys so that there are
    attached to their plugin, using the plugin class name for instance. This is done
    automatically when using the :func:`autocached` decorator on properties. This use
    the key ``{plugin class name}::{property name}``.
    """

    def _init_plugin(self) -> None:
        """Create a cache if not already created by another plugin."""
        super()._init_plugin()
        # Multiple plugins might have a cache
        # The cache is in common. Dangerous.
        if not hasattr(self, "cache"):
            self.cache: dict[str, Any] = {}
            """Cache dictionnary."""

    def clean_cache(self) -> None:
        """Clean the cache of all variables."""
        self.cache.clear()

    def set_in_cache(self, key: str, value: Any):
        """Add value to the plugin cache."""
        self.cache[key] = value

    def _key_error(self, key: str):
        """Raise slightly more informative message on cache miss."""
        name = self.ID or self.SHORTNAME or self.__class__.__name__
        raise KeyError(f"Key '{key}' not found in cache of dataset '{name}'.")

    def get_cached(self, key: str) -> Any:
        """Get value from the cache."""
        if key in self.cache:
            return self.cache[key]
        self._key_error(key)

    def pop_from_cache(self, key: str) -> Any:
        """Remove key from the cache and return its value."""
        if key in self.cache:
            return self.cache.pop(key)
        self._key_error(key)


# Typevar to preserve autocached properties' type.
R = TypeVar("R")


# The `func` argument is typed as Any because technically Callable is contravariant
# and typing it as Plugin would not allow subclasses.
def autocached(func: Callable[[Any], R]) -> Callable[[Any], R]:
    """Make a property auto-cached.

    If the variable of the same name is in the cache, return its cached value
    immediately. Otherwise run the code of the property and cache the return value.
    """
    try:
        qualpath = func.__qualname__.split(".")[:-1]
        qualname = ".".join(qualpath)
    except Exception:
        qualname = ""

    name = "::".join([qualname, func.__name__])

    @functools.wraps(func)
    def wrapper(self: Any) -> R:
        if name in self.cache:
            return self.get_cached(name)
        value = func(self)
        self.set_in_cache(name, value)
        return value

    return wrapper
