"""Definition of base Module for the interface."""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, overload

from neba.utils import get_classname

if TYPE_CHECKING:
    from .interface import DataInterface
    from .params import ParametersAbstract

log = logging.getLogger(__name__)


class Module:
    """Module to which the data-manager delegates some functionality."""

    _is_setup: bool = False
    """Keep track if the module has been set up."""

    di: DataInterface
    """Parent interface."""

    @property
    def parameters(self) -> ParametersAbstract:
        """Quick access to the parameters module."""
        return self.di.parameters

    def __init__(self, params: Any | None = None, **kwargs: Any) -> None:
        pass

    def __repr__(self) -> str:
        lines = self._lines()
        if not lines:
            lines.append(get_classname(self))
        return "\n".join(lines)

    def _lines(self) -> list[str]:
        """Lines to show in interface repr (human readable)."""
        return []

    def setup(self) -> None:
        """Initialize module."""
        pass


class CachedModule(Module):
    """Module containing a cache.

    The cache is voided on a call of :meth:`.DataInterface.trigger_callbacks`. This is
    typically done everytime the parameters change.
    """

    _add_void_callback = True

    def setup(self) -> None:
        """Set up cache.

        Add a callback to the parent interface that will void the cache when called.
        """
        cls_name = get_classname(self)
        log.debug("Setting up cache for %s", cls_name)
        self.cache: dict[str, Any] = {}

        def callback(di: DataInterface, **kwargs: Any) -> None:
            self.void_cache()

        if self._add_void_callback:
            key = f"void_cache[{cls_name}]"
            self.di.register_callback(key, callback)

    def void_cache(self) -> None:
        """Clear the cache."""
        self.cache.clear()


# Typevar to preserve autocached properties' type.
R = TypeVar("R")
T_CachedMod = TypeVar("T_CachedMod", bound=CachedModule)


def autocached(
    func: Callable[[T_CachedMod], R],
) -> Callable[[T_CachedMod], R]:
    """Make a method autocached.

    When the method is accessed, it will first check if a key with the same name (as
    the property) exists in the module cache. If yes, it directly returns the cached
    values, otherwise it runs the code of the method, caches the result and returns
    it.

    There is no check on the module containing a cache. If not it will raise an
    AttributeError on accessing the method.

    This also works for properties. Make sure you autocache the method first::

        @property
        @autocached
        def my_property(self): ...
    """
    property_name = func.__name__

    @functools.wraps(func)
    def wrap(self: T_CachedMod) -> R:
        if property_name in self.cache:
            return self.cache[property_name]
        result = func(self)
        self.cache[property_name] = result
        return result

    return wrap


T_Mod = TypeVar("T_Mod", bound=Module)


class ModuleMix(Generic[T_Mod], Module):
    """A module containing multiple other modules.

    This can allow to combine modules to collect different sources, write multiple
    time in different manners, etc.

    This is an abstract class and should be used as a base for creating specific mixes.
    This abstract class initialize every module in the mix.
    Mixes are intended to be instantiated with the class method :meth:`create`.
    """

    T_Self = TypeVar("T_Self", bound="ModuleMix[T_Mod]")

    base_types: tuple[type[T_Mod], ...] = ()
    """Tuple of types of the constituting modules."""
    base_modules: dict[str, T_Mod]
    """List of module instances."""

    select_func: Callable[..., str] | None = None

    _auto_dispatch_getattr: bool = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # initialize every base module
        self.base_modules = {}
        for cls in self.base_types:
            name = cls.__name__
            if name in self.base_modules:
                raise KeyError(f"There are multiple modules with the class name {name}")
            self.base_modules[name] = cls(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Dispatch to base module if they have the attribute defined.

        This gets called if __getattribute__ fails, ie the attribute is not defined
        on this instance.
        """
        if not self._auto_dispatch_getattr:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

        try:
            selected = self.select()
        except Exception as e:
            raise AttributeError(
                f"Could not select a module for accessing attribute '{name}'"
            ) from e

        if not hasattr(selected, name):
            raise AttributeError(
                f"Selected base module '{selected}' has no attribute '{name}' defined."
            )
        return getattr(selected, name)

    def setup(self) -> None:
        """Set up all base modules."""
        for mod in self.base_modules.values():
            mod.di = self.di
            mod.setup()

    @classmethod
    def create(
        cls: type[T_Self],
        bases: Sequence[type[T_Mod]],
        select_func: Callable[..., str] | None = None,
    ) -> type[T_Self]:
        """Create a new mix-class from base module.

        bases
            Module types to mix.
        select_func
            Function to select one of the base module depending on the current module
            state, and data-manager parameters. It receives the instance of the module
            mix and additional kwargs, and must return the class-name of one of the
            base module.
        """
        cls.base_types = tuple(bases)
        if select_func is not None:
            cls.select_func = select_func
        return cls

    @classmethod
    def set_select(cls: type[T_Self], select_func: Callable[..., str]) -> None:
        """Set the selection function.

        select_func
            Function to select one of the base module depending on the current module
            state, and data-manager parameters. It receives the instance of the module
            mix and additional kwargs, and must return the class-name of one of the
            base module.
        """
        cls.select_func = select_func

    def _lines(self) -> list[str]:
        s = []
        for name, mod in self.base_modules.items():
            lines = [f"\t{line}" for line in mod._lines()]
            if lines:
                s.append(name)
                s += lines
        return s

    def select(self, **kwargs: Any) -> T_Mod:
        """Return the module to select under current module and data-manager state.

        Parameters
        ----------
        kwargs
            Will be passed to the selection function.
        """
        if self.select_func is None:
            raise ValueError(f"No selection function registered for {self.__class__}.")
        # temporarily desactivate auto dispatch to avoid endless recursion if
        # select_func has AttributeErrors (error message will be easier to understand)
        old = self._auto_dispatch_getattr
        self._auto_dispatch_getattr = False
        try:
            if inspect.ismethod(self.select_func):
                selected = self.select_func(**kwargs)
            else:
                selected = self.select_func(self, **kwargs)
        finally:
            self._auto_dispatch_getattr = old
        return self.base_modules[selected]

    def apply_all(self, method: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Get results from every base module.

        Every output is put in a list if not already.
        """
        groups: list[Any] = []
        for mod in self.base_modules.values():
            output = getattr(mod, method)(*args, **kwargs)
            groups.append(output)
        return groups

    def apply_select(
        self,
        method: str,
        *args: Any,
        select: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        """Get result from a single base module.

        Module is selected with :attr:`select_func`, based on current module and
        data-manager state.

        Parameters
        ----------
        method
            Method name to run
        args, kwargs
            Passed to the method
        select
            Mapping of parameters passed to the selection function.
        """
        if select is None:
            select = {}
        mod = self.select(**select)
        return getattr(mod, method)(*args, **kwargs)

    @overload
    def apply(
        self,
        method: str,
        all: Literal[True],
        *args: Any,
        select: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Any]: ...

    @overload
    def apply(
        self,
        method: str,
        all: Literal[False],
        *args: Any,
        select: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any: ...

    @overload
    def apply(
        self,
        method: str,
        all: bool,
        *args: Any,
        select: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any | list[Any]: ...

    def apply(
        self,
        method: str,
        all: bool,
        *args: Any,
        select: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any | list[Any]:
        """Get results from all or one of the base modules.

        Parameters
        ----------
        method
            Method name to run
        all
            If True, return results from *all* modules, otherwise only from a selected
            one.
        args, kwargs
            Passed to the method
        select
            Mapping of parameters passed to the selection function.
        """
        if all:
            return self.apply_all(method, *args, **kwargs)
        return self.apply_select(method, *args, select=select, **kwargs)
