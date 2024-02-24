"""Dataset objects.

The Dataset object is the main entry point for the user. By subclassing it,
they can adapt it to their data quickly.

If we want to retain the ability to define a new dataset just by subclassing
the main class, this makes splitting features into different classes challenging.
I still tried to use composition and delegate some work by "modules": FileManager,
Loader, and Writer. These retain a reference to the Dataset and can invoke
attributes and methods from it, which can be user-defined in a subclass.

I tried to stay agnostic to how a module may work to possibly accomodate for different
data formats, sources, etc. A minimal API is written in each abstract class.
It may still be quite geared towards multifiles-netcdf, since this is what I had in mind
when writing it. But hopefully it should be easy to swap modules without breaking
everything.

The parameters management is kept in the Dataset object for simplicity, maybe it
could be done by a module of its own, if this is necessary.

Modules all inherit from :class:`module.Module`, which features a caching system, with
even some attribute that can generate a new value on the fly in case of a cache
miss (see AutoCachedProperty). This was done to avoid numerous computations when
dealing with multi-files scanners.
The Dataset can trigger a flush of all caches.
"""
from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping, Sequence
from typing import Any, Generic, TypeVar, TypeAlias


from data_assistant.config import Scheme
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    _DB: TypeAlias = "DatasetBase"
else:
    _DB = object


class Module(_DB):
    def _init_module(self) -> None:
        pass


_DataT = TypeVar("_DataT")
_SourceT = TypeVar("_SourceT")


class DatasetBase(Generic[_DataT, _SourceT]):
    SHORTNAME: str | None = None
    """Short name to refer to this dataset class."""
    ID: str | None = None
    """Long name to identify uniquely this dataset class."""

    PARAMS_NAMES: Sequence[Hashable] = []
    """List of known parameters names."""
    PARAMS_DEFAULTS: dict = {}
    """Default values of parameters.

    Optional. Can be used to define default values for parameters local to a
    dataset, (*ie* that are not defined in project-wide
    :class:`ParametersManager`).
    """

    def __init__(
        self, params: Mapping[str, Any] | Scheme | None = None, **kwargs
    ) -> None:
        self.params: dict[str, Any] = {}
        """Mapping of current parameters values.

        They should be changed by using :meth:`set_params` to void the cached values
        appropriately.
        """

        self.set_params(params, **kwargs)

        # Initianlize modules in base classes
        for cls in self.__class__.__bases__:
            if issubclass(cls, Module):
                cls._init_module(self)  # type: ignore

    def set_params(
        self,
        params: Mapping[str, Any] | Scheme | None = None,
        **kwargs,
    ):
        """Set parameters values.

        Parameters
        ----------
        params:
            Mapping of the parameters names to their values.
        kwargs:
            Other parameters values in the form ``name=value``.
            Parameters will be taken in order of first available in:
            ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
        """
        if params is None:
            params = {}
        elif isinstance(params, Scheme):
            params = dict(params.values_recursive())
        else:
            params = dict(params)  # shallow copy
        params = params | self.PARAMS_DEFAULTS
        params.update(kwargs)

        self.params.update(params)
        # TODO Check if features are present (use protocol ?)
        # self.clean_cache()
        # self.check_known_param(params)

    def __str__(self) -> str:
        """Return a string representation."""
        name = []
        if self.SHORTNAME is not None:
            name.append(self.SHORTNAME)
        if self.ID is not None:
            name.append(self.ID)

        clsname = self.__class__.__name__
        if name:
            clsname = f" ({clsname})"

        return ":".join(name) + clsname

    def __repr__(self) -> str:
        """Return a human readable representation."""
        s = []
        s.append(self.__str__())
        s.append("Parameters:")
        s.append(f"\tdefined: {self.PARAMS_NAMES}")
        if self.PARAMS_DEFAULTS:
            s.append(f"\tdefaults: {self.PARAMS_DEFAULTS}")
        # s.append(f"\tallowed: {self.allowed_params}")
        s.append(f"\tset: {self.params}")

        # TODO check HasFileManager ? with protocol or type ?
        # try except ?
        # if self.file_manager is not None:
        #     s += str(self.file_manager).splitlines()

        return "\n".join(s)

    def get_source(self) -> _SourceT:
        raise NotImplementedError("Implement in a subclass or Mixin.")

    def get_data(self) -> _DataT:
        raise NotImplementedError("Implement in a subclass or Mixin.")

    def get_data_sets(
        self,
        params_maps: Sequence[Mapping[str, Any]] | None = None,
        params_sets: Sequence[Sequence] | None = None,
        **kwargs,
    ) -> _DataT | Iterable[_DataT]:
        return self.get_data(**kwargs)

    # def check_known_param(self, params: Iterable[str]):
    #     """Check if the parameters are known to this dataset class.

    #     A 'known parameter' is one present in :attr:`PARAMS_NAMES` or defined
    #     in the filename pattern (as a varying group).

    #     Only run the check if :attr:`exact_params` is True.
    #     """
    #     if not self.exact_params:
    #         return
    #     for p in params:
    #         if p not in self.allowed_params:
    #             raise KeyError(f"Parameter '{p}' was not expected for dataset {self}")
