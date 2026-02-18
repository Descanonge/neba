"""The main class for interfacing with your data."""

from __future__ import annotations

import copy
import logging
import typing as t
from collections import abc

from traitlets import Bunch

from neba.config.section import Section

from .loader import LoaderAbstract
from .module import CachedModule, Module
from .params import ParametersAbstract
from .source import SourceAbstract
from .types import T_Data, T_Params, T_Source
from .writer import WriterAbstract

log = logging.getLogger(__name__)


class DataInterface(t.Generic[T_Params, T_Source, T_Data]):
    """Define how to interface with data.

    Delegates features to modules for parameters management, source management, data
    loading, and data writing.
    """

    # -- Interface Identification --

    SHORTNAME: str | None = None
    """Short name to refer to this data-manager class."""
    ID: str | None = None
    """Long name to identify uniquely this data-manager class."""

    # -- Module related --

    _modules_attributes: dict[str, str] = dict(
        parameters="Parameters",
        source="Source",
        loader="Loader",
        writer="Writer",
    )
    """Mapping from the instance attribute to type attribute.

    Modules will instanciate and setup in this order. Parameters should be first.
    """

    _modules: dict[str, Module]
    """Mapping from attribute names to module instances. Filled during initialization."""

    # Default module types
    Parameters: type[ParametersAbstract] = ParametersAbstract
    Source: type[SourceAbstract] = SourceAbstract
    Loader: type[LoaderAbstract] = LoaderAbstract
    Writer: type[WriterAbstract] = WriterAbstract

    # -- Instance attributes --
    parameters: ParametersAbstract[T_Params]
    source: SourceAbstract[T_Source]
    loader: LoaderAbstract[T_Source, T_Data]
    writer: WriterAbstract[T_Source, T_Data]

    _reset_callbacks: dict[str, abc.Callable[..., None]]
    """Dictionary of callbacks to run when parameters are changed/reset.

    Callbacks should be functions that take the interface as first argument, then any
    number of keyword arguments.
    """

    def __init__(self, params: t.Any | None = None, **kwargs: t.Any) -> None:
        self._modules = {}
        self._reset_callbacks = {}

        self._instantiate_modules(params, **kwargs)

        # backref
        for mod in self._modules.values():
            mod.di = self

        # Setup modules
        # Start with parameters.
        self.parameters.setup_safe(raise_errors=True)

        # Parameters won't initialize again
        for mod in self._modules.values():
            mod.setup_safe()

    def _instantiate_modules(self, *args: t.Any, **kwargs: t.Any) -> None:
        for instance_attr, type_attr in self._modules_attributes.items():
            # None means the user has deleted module without unregistering it, fine.
            mod_type = getattr(self, type_attr, None)
            if mod_type is None:
                log.info("Module %%s registered but definition not present.", type_attr)
                return

            try:
                mod = mod_type(*args, **kwargs)
            except Exception as e:
                log.warning("Error when instantiating module %s", mod_type, exc_info=e)
                if not mod_type._allow_instantiation_failure:
                    raise e
            else:
                self._modules[instance_attr] = mod
                setattr(self, instance_attr, mod)

    def __str__(self) -> str:
        """Return a string representation."""
        name = []
        if self.SHORTNAME is not None:
            name.append(self.SHORTNAME)
        if self.ID is not None:
            name.append(self.ID)

        cls_name = self.__class__.__name__
        if name:
            cls_name = f" ({cls_name})"

        return ":".join(name) + cls_name

    def __repr__(self) -> str:
        """Return a human readable representation."""
        s = [self.__str__()]
        for mod in self._modules.values():
            s += mod._lines()
        return "\n".join(s)

    def save_excursion(self, save_cache: bool = False) -> _ParamsContext:
        """Save and restore current parameters after a with block.

        For instance::

            # we have some parameters, self.parameters["p"] = 0
            with self.save_excursion():
                # we change them
                self.parameters["p"] = 2
                self.get_data()

            # we are back to self.parameters["p"] = 0

        Any exception happening in the with block will be raised.

        Parameters
        ----------
        save_cache:
            If true, save and restore the cache. This may lead to unexpected behavior
            and is disabled by default.

        Returns
        -------
        context
            Context object containing the original parameters.
        """
        return _ParamsContext(self, save_cache)

    # - end of parameters methods

    def register_callback(self, key: str, func: abc.Callable[..., None]) -> None:
        """Register a new callback. Throw error if it already exists."""
        if key in self._reset_callbacks:
            raise KeyError(
                f"Reset callback '{key}' already exists ({self._reset_callbacks[key]})."
            )
        self._reset_callbacks[key] = func

    def trigger_callbacks(
        self, callbacks: bool | list[str] = True, **kwargs: t.Any
    ) -> None:
        """Call all registered callbacks.

        Modules should register callback in the dictionary :attr:`_reset_callbacks`
        during :meth:`~.Module.setup`.

        Parameters
        ----------
        callbacks
            If True all callbacks are run (default), if False none are run. Can also
            be a list of specific callback names to run (keys in the dictionary
            :attr:`_reset_callbacks`).
        """
        if callbacks is False:
            return
        if callbacks is True:
            callbacks = list(self._reset_callbacks.keys())

        for key in callbacks:
            callback = self._reset_callbacks[key]
            callback(self, **kwargs)

    def get_source(self, *args: t.Any, **kwargs: t.Any) -> T_Source | list[T_Source]:
        """Return source for the data.

        Can be filenames, URL, store object, etc.

        Wraps around ``source.get_source()``.
        """
        return self.source.get_source(*args, **kwargs)

    def get_data(self, *args: t.Any, **kwargs: t.Any) -> T_Data:
        """Return data object.

        Wraps around ``loader.get_data()``.
        """
        return self.loader.get_data(*args, **kwargs)

    def write(self, *args: t.Any, **kwargs: t.Any) -> t.Any:
        """Write data to target.

        Wraps around ``writer.write()``.
        """
        return self.writer.write(*args, **kwargs)

    def get_data_sets(
        self,
        params_maps: abc.Sequence[abc.Mapping[str, t.Any]] | None = None,
        params_sets: abc.Sequence[abc.Sequence] | None = None,
        **kwargs: t.Any,
    ) -> T_Data | list[T_Data]:
        """Return data for specific sets of parameters.

        Each set of parameter will specify one filename. Parameters that do not change
        from one set to the next do not need to be specified if they are fixed (by
        setting them in the interface). The sets can be specified with either one of
        `params_maps` or `params_sets`.

        Parameters
        ----------
        params_maps
            Each set is specified by a mapping of parameters names to a value::

                [{'Y': 2020, 'm': 1, 'd': 15},
                 {'Y': 2021, 'm': 2, 'd': 24},
                 {'Y': 2022, 'm', 6, 'd': 2}]

            This will give 3 filenames for 3 different dates. Note that here, the
            parameters do not need to be the same for all sets, for example in a fourth
            set we could have ``{'Y': 2023, 'm': 1, 'd': 10, 'depth': 50}`` to override
            the value of 'depth' set in the interface parameters.
        params_sets
            Here each set is specified by sequence of parameters values. This first row
            gives the order of parameters. The same input as before can be written as::

                [['Y', 'm', 'd'],
                 [2020, 1, 15],
                 [2021, 2, 24],
                 [2022, 6, 2]]

            Here the changing parameters must remain the same for the whole sequence.
        kwargs
            Arguments passed to :meth:`get_data`.

        Returns
        -------
        data
            List of data objects corresponding to each set of parameters. Subclasses can
            overwrite this method to specify how to combine them into one if needed.
        """
        if params_sets is not None and params_maps is not None:
            raise KeyError("Cannot specify both params_sets and params_maps")

        if params_maps is None:
            # Turn param_sets into param_maps
            if params_sets is None:
                raise KeyError(
                    "Must at least specify one of params_sets or params_maps"
                )

            dims = params_sets[0]
            if not all(isinstance(x, str) for x in dims):
                raise TypeError(f"Dimensions names must be strings, got: {dims}")

            params_maps = []
            for p_set in params_sets[1:]:
                params_maps.append(dict(zip(dims, p_set, strict=True)))

        data = []
        with self.save_excursion():
            for p_map in params_maps:
                self.parameters.update(p_map)
                data.append(self.get_data(**kwargs))

        return data


class _ParamsContext:
    def __init__(self, di: DataInterface, save_cache: bool) -> None:
        # Save cache first, copying params might void it
        self.caches: dict = {}
        if save_cache:
            self.caches = {
                name: dict(mod.cache)
                for name, mod in di._modules.items()
                if isinstance(mod, CachedModule)
            }

        self.di = di
        self.params = copy.deepcopy(di.parameters.direct)

    def repopulate_cache(self) -> None:
        for name, saved_cache in self.caches.items():
            module = self.di._modules[name]
            assert isinstance(module, CachedModule)
            for key, val in saved_cache.items():
                module.cache[key] = val

    def __enter__(self) -> t.Self:
        return self

    def __exit__(self, *exc: t.Any) -> t.Literal[False]:
        self.di.parameters.reset()
        self.di.parameters.update(self.params)

        if self.caches is not None:
            self.repopulate_cache()

        # return false to raise any exception that may have occured
        return False


class DataInterfaceSection(DataInterface, Section):
    """An interface that is also a configurable section.

    Any modification of the interface traits will void the cache.

    Parameters
    ----------
    params:
        Passed to the parameters manager and other modules.
    kwargs:
        Traits of the interface are extracted. The rest is passed to modules as usual.
    """

    def __init__(self, params: t.Any | None = None, **kwargs: t.Any) -> None:
        # extract traits from kwargs
        config = {}
        for name in self.keys():
            if name in kwargs:
                # `name` could correspond to a parameter for the application or section,
                # rather than for the interface itself. Check things are unambiguous
                if isinstance(params, Section) and name in params.keys(
                    subsections=False, aliases=True
                ):
                    raise KeyError(
                        f"""Keyword argument '{name}' is both a trait in the parameters
                        ({params.__class__.__name__}) and the interface
                        ({self.__class__.__name__}), I cannot choose between the two."""
                    )
                config[name] = kwargs.pop(name)
        Section.__init__(self, config)
        DataInterface.__init__(self, params, **kwargs)

        # Reset on trait change
        def handler(change: Bunch) -> None:
            self.trigger_callbacks()

        for subsection in self.subsections_recursive():
            subsection.observe(handler)

    def __repr__(self) -> str:
        """Combine Inferface and Section repr."""
        interface = DataInterface.__repr__(self)
        section = Section.__repr__(self)
        # remove first line (class name), redundant
        return "\n".join([interface, *section.splitlines()[1:]])
