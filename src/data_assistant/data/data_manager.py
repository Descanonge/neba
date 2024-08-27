"""DataManager base: the main class for your dataset."""

from __future__ import annotations

import copy
import logging
import typing as t
from collections import abc

from .loader import LoaderAbstract
from .module import CachedModule, Module
from .params import ParamsManagerAbstract
from .source import SourceAbstract
from .util import T_Data, T_Params, T_Source
from .writer import WriterAbstract

log = logging.getLogger(__name__)


class AutoModulesMixin:
    """Automatically detect modules defined in the class definition."""

    _module_classes: dict[str, type[Module]] = dict()

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        cls._module_classes = dict(cls._module_classes)
        # copy for it to be unique to each subclass

        # Add anything that looks like a module
        for attr in cls.__dict__.values():
            if isinstance(attr, type) and issubclass(attr, Module):
                # Check if its ancestor type is defined/registered
                cls._module_classes[attr._ATTR_NAME] = attr

    def _init_modules(
        self, dm: DataManagerBase, params: t.Any | None = None, **kwargs
    ) -> None:
        self._modules: dict[str, Module] = {}
        for name, cls in self._module_classes.items():
            mod = cls(dm, params, **kwargs)
            setattr(dm, name, mod)
            self._modules[name] = mod


class DataManagerBase(t.Generic[T_Params, T_Source, T_Data]):
    """DataManager base object.

    The parameters (stored in :attr:`params`) are treated as global across the instance,
    and those are the value that will be used when calling various methods. Few
    methods may allow to complete them, fewer to overwrite them temporarily.
    Parameters should be changed using :meth:`set_params`, which may will the cache
    that some plugin use.
    :meth:`save_excursion` can be used to change parameters temporarily inside a `with`
    block.
    """

    SHORTNAME: str | None = None
    """Short name to refer to this data-manager class."""
    ID: str | None = None
    """Long name to identify uniquely this data-manager class."""

    params_mod: type[ParamsManagerAbstract] = ParamsManagerAbstract
    source_mod: type[SourceAbstract] = SourceAbstract
    loader_mod: type[LoaderAbstract] = LoaderAbstract
    writer_mod: type[WriterAbstract] = WriterAbstract

    params_manager: ParamsManagerAbstract[T_Params]
    source: SourceAbstract[T_Source]
    loader: LoaderAbstract[T_Source, T_Data]
    writer: WriterAbstract[T_Source, T_Data]

    def __init__(self, params: t.Any | None = None, **kwargs) -> None:
        self._reset_callbacks: dict[str, abc.Callable[..., None]] = {}
        """Dictionary of callbacks to run when parameters are changed/reset.

        Callbacks should be functions that take the data manager as first argument, then
        any number of keyword arguments.
        """

        self.params_manager = self.params_mod(self, params, **kwargs)
        self.source = self.source_mod(self, params, **kwargs)
        self.loader = self.loader_mod(self, params, **kwargs)
        self.writer = self.writer_mod(self, params, **kwargs)
        self._modules: dict[str, Module] = dict(
            params_manager=self.params_manager,
            source=self.source,
            loader=self.loader,
            writer=self.writer,
        )
        self.set_params(params, **kwargs)

    def __str__(self) -> str:
        """Return a string representation."""
        name = []
        if self.SHORTNAME is not None:
            name.append(self.SHORTNAME)
        if self.ID is not None:
            name.append(self.ID)

        try:
            cls = self.__class__
            clsname = f"{cls.__module__}.{cls.__name__}"
            if name:
                clsname = f" ({clsname})"
        except AttributeError:
            clsname = ""

        return ":".join(name) + clsname

    def __repr__(self) -> str:
        """Return a human readable representation."""
        s = [self.__str__()]
        for mod in self._modules.values():
            s += mod._lines()
        return "\n".join(s)

    @property
    def params(self) -> T_Params:
        """Parameters values for this instance."""
        return self.params_manager._params

    def set_params(
        self, params: t.Any | None = None, reset: bool | list[str] = True, **kwargs
    ):
        """Set parameters values.

        Old parameters values are discarded.

        Parameters
        ----------
        reset:
            Passed to :meth:`reset`.
        kwargs:
            Other parameters values in the form ``name=value``.
            Parameters will be taken in order of first available in:
            ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
        """
        self.params_manager.set_params(params, **kwargs)
        self.reset(reset)

    def update_params(
        self, params: t.Any | None = None, reset: bool | list[str] = True, **kwargs
    ):
        """Update one or more parameters values.

        Other parameters are kept.

        Parameters
        ----------
        reset:
            Passed to :meth:`reset`.
        kwargs:
            Other parameters values in the form ``name=value``.
        """
        self.params_manager.update_params(params, **kwargs)
        self.reset(reset)

    def save_excursion(self, save_cache: bool = False) -> _ParamsContext:
        """Save and restore current parameters after a with block.

        For instance::

            # we have some parameters, self.params["p"] = 0
            with self.save_excursion():
                # we change them
                self.set_params(p=2)
                self.get_data()

            # we are back to self.params["p"] = 0

        Any exception happening in the with block will be raised.

        Parameters
        ----------
        save_cache:
            If true, save and restore the cache. The context reset the parameters of the
            data manager using :meth:`set_params` and then restore any saved key in the
            cache, *without overwriting*. This may lead to unexpected behavior and is
            disabled by default.

        Returns
        -------
        context
            Context object containing the original parameters.
        """
        return _ParamsContext(self, save_cache)

    # - end of parameters methods

    def _register_callback(self, key: str, func: abc.Callable[..., None]):
        """Register a new callback. Throw error if it already exists."""
        if key in self._reset_callbacks:
            raise KeyError(
                f"Reset callback '{key}' already exists ({self._reset_callbacks[key]})."
            )
        self._reset_callbacks[key] = func

    def reset(self, callbacks: bool | list[str] = True, **kwargs):
        """Call all registered callbacks when parameters are reset/changed.

        Plugins should register callback in the dictionary :attr:`_RESET_CALLBACKS`
        during :meth:`~.plugin.Plugin._init_plugin`.
        Callbacks should be functions that take the data manager as first argument, then
        any number of keyword arguments.

        Parameters
        ----------
        callbacks
            If True all callbacks are run (default), if False none are run. Can also
            be a list of specific callback names to run (keys in the dictionary
            :attr:`_RESET_CALLBACKS`).
        """
        if callbacks is False:
            return
        if callbacks is True:
            callbacks = list(self._reset_callbacks.keys())

        for key in callbacks:
            callback = self._reset_callbacks[key]
            callback(self, **kwargs)

    def get_source(self, *args, **kwargs) -> T_Source:
        """Return source for the data.

        Can be filenames, URL, store object, etc.

        Wraps around ``source.get_source()``.
        """
        return self.source.get_source(*args, **kwargs)

    def get_data(self, *args, **kwargs) -> T_Data:
        """Return data object.

        Wraps around ``loader.get_data()``.
        """
        return self.loader.get_data(*args, **kwargs)

    def write(self, *args, **kwargs) -> t.Any:
        """Write data to target.

        Wraps around ``writer.write()``.
        """
        return self.writer.write(*args, **kwargs)

    def get_data_sets(
        self,
        params_maps: abc.Sequence[abc.Mapping[str, t.Any]] | None = None,
        params_sets: abc.Sequence[abc.Sequence] | None = None,
        **kwargs,
    ) -> T_Data | list[T_Data]:
        """Return data for specific sets of parameters.

        Each set of parameter will specify one filename. Parameters that do not change
        from one set to the next do not need to be specified if they are fixed (by
        setting them in the DataManager). The sets can be specified with either one of
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
            the value of 'depth' set in the DataManager parameters.
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

        data: list[T_Data] = []
        with self.save_excursion():
            for p_map in params_maps:
                self.set_params(p_map)
                data.append(self.get_data(**kwargs))

        return data


class _ParamsContext:
    def __init__(self, dm: DataManagerBase, save_cache: bool):
        self.dm = dm
        self.params = copy.deepcopy(dm.params)
        self.caches: dict | None = None

        if save_cache:
            self.caches = {
                name: mod.cache
                for name, mod in dm._modules.items()
                if isinstance(mod, CachedModule)
            }

    def repopulate_cache(self):
        for module, save in self.caches.items():
            cache = self._mod(module).cache
            for key, val in save.items():
                # do not overwrite current cache
                if key not in cache:
                    cache[key] = val
                    continue

                # check that there is correspondance with saved and current cache
                current_val = save[key]
                if current_val != val:
                    log.warning(
                        "Different value when restoring module %s cache for key %s: "
                        "saved '%s', has '%s'.",
                        module,
                        key,
                        str(val),
                        str(current_val),
                    )

    def __enter__(self) -> t.Self:
        return self

    def __exit__(self, *exc):
        self.dm.set_params(self.params)

        if self.caches is not None:
            self.repopulate_cache()

        # return false to raise any exception that may have occured
        return False
