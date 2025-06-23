"""Definition of base Module for the DataManager."""

from __future__ import annotations

import functools
import logging
import typing as t
from collections import abc

if t.TYPE_CHECKING:
    from .data_manager import Dataset

log = logging.getLogger(__name__)


class Module:
    """Module to which the data-manager delegates some functionality."""

    _allow_instantiation_failure: bool = True
    """Wether exception will be raised or not during instantiation."""
    _is_setup: bool = False
    """Keep track if the module has been set up."""

    dm: Dataset
    """Parent dataset."""

    @property
    def params(self) -> t.Any:
        """Parameters of the data manager."""
        return self.dm.params_manager.params

    def __init__(self, params: t.Any | None = None, **kwargs):
        pass

    def __repr__(self) -> str:
        return "\n".join(self._lines())

    def _lines(self) -> list[str]:
        """Lines to show in DataManager repr (human readable)."""
        return []

    def setup(self) -> None:
        """Initialize module, allow for cooperation in inheritance.

        It will be called on ancestors from every parent class. It is still necessary to
        include a ``super.setup()`` where necessary.
        """
        pass

    def _setup_ancestors(self) -> None:
        """Initialize module, allow for cooperation in inheritance.

        Will only run if :attr:`_is_setup` is False.
        """
        if self._is_setup:
            return

        initialized: list[type[Module]] = list()
        for ancestor in self.__class__.mro():
            if issubclass(ancestor, Module) and ancestor not in initialized:
                try:
                    ancestor.setup(self)
                except Exception as e:
                    log.warning(
                        "Error when initializing module %s (%s)",
                        self,
                        ancestor,
                        exc_info=e,
                    )
                initialized += ancestor.mro()
        self._is_setup = True


class CachedModule(Module):
    """Plugin containing a cache.

    The cached-module cache is voided on a call of :meth:`.DataManagerBase.reset`.
    This is typically done everytime the parameters change.
    """

    _add_void_callback = True

    def setup(self) -> None:
        self.cache: dict[str, t.Any] = {}

        def callback(dm, **kwargs) -> None:
            self.void_cache()

        if self._add_void_callback:
            key = f"void_cache[{self.__class__.__name__}]"
            self.dm._register_callback(key, callback)

    def void_cache(self) -> None:
        """Clear the cache."""
        self.cache.clear()


# Typevar to preserve autocached properties' type.
R = t.TypeVar("R")
T_CachedMod = t.TypeVar("T_CachedMod", bound=CachedModule)


# The `func` argument is typed as Any because technically Callable is contravariant
# and typing it as Module would not allow subclasses.
def autocached(
    func: abc.Callable[[T_CachedMod], R],
) -> abc.Callable[[T_CachedMod], R]:
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
    def wrap(self: T_CachedMod) -> R:
        if property_name in self.cache:
            return self.cache[property_name]
        result = func(self)
        self.cache[property_name] = result
        return result

    return wrap


T_Mod = t.TypeVar("T_Mod", bound=Module)


class ModuleMix(t.Generic[T_Mod], Module):
    """A module containing multiple other modules.

    This can allow to combine modules to collect different sources, write multiple
    time in different manners, etc.

    This is an abstract class and should be used as a base for creating specific mixes.
    This abstract class initialize every module in the mix.
    Mixes are intended to be instantiated with the class method :meth:`create`.
    """

    T_Self = t.TypeVar("T_Self", bound="ModuleMix[T_Mod]")

    base_types: tuple[type[T_Mod], ...] = ()
    """Tuple of types of the constituting modules."""
    base_modules: dict[str, T_Mod]
    """List of module instances."""

    select_func: abc.Callable[..., str] | None = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # initialize every base module
        self.base_modules = {}
        for cls in self.base_types:
            self.base_modules[cls.__name__] = cls(*args, **kwargs)

    def _init_module(self) -> None:
        for mod in self.base_modules.values():
            mod.dm = self.dm
            mod.setup()

    @classmethod
    def create(
        cls: type[T_Self],
        bases: abc.Sequence[type[T_Mod]],
        select_func: abc.Callable[..., str] | None = None,
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
            cls.select_func = select_func  # type: ignore
        return cls

    @classmethod
    def set_select(cls: type[T_Self], select_func: abc.Callable[..., str]):
        """Set the selection function.

        select_func
            Function to select one of the base module depending on the current module
            state, and data-manager parameters. It receives the instance of the module
            mix and additional kwargs, and must return the class-name of one of the
            base module.
        """
        cls.select_func = select_func  # type: ignore

    def _lines(self) -> list[str]:
        s = []
        for name, mod in self.base_modules.items():
            lines = [f"\t{line}" for line in mod._lines()]
            if lines:
                s.append(name)
                s += lines
        return s

    def select(self, **kwargs) -> T_Mod:
        """Return the module to select under current module and data-manager state.

        Parameters
        ----------
        kwargs
            Will be passed to the selection function.
        """
        if self.select_func is None:
            raise ValueError(f"No selection function registered for {self.__class__}.")
        selected = self.select_func(self, **kwargs)
        return self.base_modules[selected]

    def apply_all(self, method: str, *args, **kwargs) -> list[t.Any]:
        """Get results from every base module.

        Every output is put in a list if not already.
        """
        groups: list[t.Any] = []
        for mod in self.base_modules.values():
            output = getattr(mod, method)(*args, **kwargs)
            groups.append(output)
        return groups

    def apply_select(
        self, method: str, *args, select: dict[str, t.Any] | None = None, **kwargs
    ) -> list[t.Any]:
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

    @t.overload
    def apply(
        self,
        method: str,
        all: t.Literal[True],
        *args,
        select: dict[str, t.Any] | None = None,
        **kwargs,
    ) -> list[t.Any]: ...

    @t.overload
    def apply(
        self,
        method: str,
        all: t.Literal[False],
        *args,
        select: dict[str, t.Any] | None = None,
        **kwargs,
    ) -> t.Any: ...

    @t.overload
    def apply(
        self,
        method: str,
        all: bool,
        *args,
        select: dict[str, t.Any] | None = None,
        **kwargs,
    ) -> t.Any | list[t.Any]: ...

    def apply(
        self,
        method: str,
        all: bool,
        *args,
        select: dict[str, t.Any] | None = None,
        **kwargs,
    ) -> t.Any | list[t.Any]:
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
