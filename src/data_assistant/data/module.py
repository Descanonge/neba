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
    _ATTR_NAME: str

    def __init__(self, dm: DataManagerBase, *args, **kwargs):
        self.dm = dm
        self._init_module()

    @property
    def params(self) -> t.Any:
        return self.dm.params_manager.params

    def _init_module(self) -> None:
        pass

    def _lines(self) -> list[str]:
        """Lines to show in DataManager repr (human readable)."""
        return []


class CachedModule(Module):
    """Plugin containing a cache."""

    def _init_module(self) -> None:
        self.cache: dict[str, t.Any] = {}

        # Voiding callback
        # we make sure to avoid late-binding by using functools.partial
        def callback(dm, **kwargs) -> None:
            mod = getattr(dm, self._ATTR_NAME)
            mod.void_cache()

        key = f"void_cache[{self.__class__.__name__}]"
        self.dm._register_callback(key, callback)

    def void_cache(self) -> None:
        self.cache.clear()


# Typevar to preserve autocached properties' type.
R = t.TypeVar("R")


# The `func` argument is typed as Any because technically Callable is contravariant
# and typing it as Module would not allow subclasses.
def autocached(func: abc.Callable[[t.Any], R]) -> abc.Callable[[t.Any], R]:
    """Make a property autocached.

    When the property is accessed, it will first check if a key with the same name (as
    the property) exists in the module cache. If yes, it directly returns the cached
    values, otherwise it runs the code of the property, caches the result and returns
    it.

    There is no check on the module containing a cache. If not it will raise an
    AttributeError on accessing the property.
    """
    property_name = func.__name__

    @functools.wraps(func)
    def wrap(self: t.Any) -> R:
        if property_name in self.cache:
            return self.cache[property_name]
        result = func(self)
        self.cache[property_name] = result
        return result

    return wrap


T_Mod = t.TypeVar("T_Mod", bound=Module)


class ModuleMix(t.Generic[T_Mod], Module):
    _base_modules: tuple[type[T_Mod], ...] = ()

    base_modules: list[T_Mod]

    def __init__(self, dm: DataManagerBase, *args, **kwargs):
        super().__init__(dm, *args, **kwargs)
        # initialize every base module
        self.base_modules = []
        for cls in self._base_modules:
            self.base_modules.append(cls(dm, *args, **kwargs))

    @classmethod
    def create(cls, bases: abc.Sequence[type[T_Mod]]) -> type[t.Self]:
        """Create a new mix-class from base module."""
        cls._base_modules = tuple(bases)
        cls._ATTR_NAME = bases[0]._ATTR_NAME

        names = [b._ATTR_NAME for b in bases]
        if any(n != n[0] for n in names):
            log.warning(
                "Mix of modules have differing attributes names (%s). Taking first one. ",
                ", ".join(names),
            )

        return cls
