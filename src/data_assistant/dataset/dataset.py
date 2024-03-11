"""DataManager base.

The DataManager object is the main entry point for the user. The base object
(:class:`DataManagerBase`) should be completed with mixins classes called
:class:`modules<module.Module>` that add various functionalities. The user can choose
modules, or/and then overwrite methods and attributes of a single class to adapt it to
their data quickly.


The DataManager base and the modules were made to be as agnostic as possible concerning
the data type, source format, etc. A minimal API is written in each abstract class that
should allow inter-operation between different modules. Hopefully this can accomodate a
variety of datasets, and it should be possible to swap modules without breaking
everything.

The parameters management is kept in the DataManager object for simplicity, maybe it
could be done by a module of its own, if this is necessary.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from typing import Any, Generic, Self, TypeVar

from data_assistant.config import Scheme

from .module import HasCache, Module

_DataT = TypeVar("_DataT")
"""Type of data (numpy, pandas, xarray, etc.)."""
_SourceT = TypeVar("_SourceT")
"""Type of the data source (filename, URL, object, etc.)."""


"""
Note on this mixins architecture.

I tried to use what could be thought as a more natural structure using composition and
by making modules attributes of the datamanager base, instead of mixins.
Problem is if the user wants to overwrite a method to adapt to their dataset, it would
be logically bound in a module: difficult to overwrite quickly to create a new
data-manager class. The solution was to allow modules to state methods to be defined on
the data-manager. The module would keep a reference of the central data-manager object
and execute methods on it. But this makes it difficult to specify
the methods precise signature, and is quite confusing in the end...
"""


class DataManagerBase(Generic[_DataT, _SourceT]):
    """DataManager base object.

    Add functionalities by subclassing it and adding mixin modules.

    The base class manages the parameters mainly via :meth:`set_params`, and specify
    entry points to be implemented by modules: :meth:`get_source` and :meth:`get_data`.

    It is excepected that the user chooses modules adapted to their needs and dataset
    formats, and create subclasses overwritting methods to further specify details
    about their datasets.
    Each subclass is thus associated to a particular dataset. Each instance of that
    subclass is associated to specific parameters: only one year, or one value of
    this or that parameter, etc.

    The parameters (stored in :attr:`params`) are treated as global across the instance,
    and those are the value that will be used when calling various methods. Few
    methods may allow to complete them, fewer to overwrite them temporarily.
    Parameters should be changed using :meth:`set_paramas`, which may will the cache
    that some module use.
    :meth:`save_excursion` can be used to change parameters temporarily inside a `with`
    block.
    """

    SHORTNAME: str | None = None
    """Short name to refer to this data-manager class."""
    ID: str | None = None
    """Long name to identify uniquely this data-manager class."""

    PARAMS_NAMES: Sequence[Hashable] = []
    """List of known parameters names."""
    PARAMS_DEFAULTS: dict = {}
    """Default values of parameters.

    Optional. Can be used to define default values for parameters local to a
    data-manager, (*ie* that are not defined in project-wide with
    :mod:`data_assistant.config`).
    """

    def __init__(
        self, params: Mapping[str, Any] | Scheme | None = None, **kwargs
    ) -> None:
        self.params: dict[str, Any] = {}
        """Mapping of current parameters values.

        They should be changed by using :meth:`set_params` to void the cached values
        appropriately.
        """

        # Initianlize modules in base classes
        for cls in self.__class__.__bases__:
            if issubclass(cls, Module):
                cls._init_module(self)  # type: ignore

        self.set_params(params, **kwargs)

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

        # can also be done via a faster hasattr check
        if isinstance(self, HasCache):
            self.clean_cache()
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
        """Return source for the data.

        Can be filenames, URL, store object, etc.
        """
        raise NotImplementedError("Implement in a subclass or Mixin.")

    def get_data(self) -> _DataT:
        """Return data object."""
        raise NotImplementedError("Implement in a subclass or Mixin.")

    def get_data_sets(
        self,
        params_maps: Sequence[Mapping[str, Any]] | None = None,
        params_sets: Sequence[Sequence] | None = None,
        **kwargs,
    ) -> _DataT | Iterable[_DataT]:
        return self.get_data(**kwargs)

    # def check_known_param(self, params: Iterable[str]):
    #     """Check if the parameters are known to this data-manager class.

    #     A 'known parameter' is one present in :attr:`PARAMS_NAMES` or defined
    #     in the filename pattern (as a varying group).

    #     Only run the check if :attr:`exact_params` is True.
    #     """
    #     if not self.exact_params:
    #         return
    #     for p in params:
    #         if p not in self.allowed_params:
    #             raise KeyError(f"Parameter '{p}' was not expected for dataset {self}")
