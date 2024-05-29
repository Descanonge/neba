"""Parameters management plugins."""

from __future__ import annotations

import copy
import logging
import typing as t
from collections import abc

from ..config.scheme import Scheme
from .plugin import CachePlugin, Plugin

log = logging.getLogger(__name__)


class ParamsPluginAbstract(Plugin):
    """Abstract class for basic parameter management."""

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


class ParamsMappingPlugin(ParamsPluginAbstract):
    """Parameters are stored in a dictionary."""

    PARAMS_DEFAULTS: dict[str, t.Any] = {}

    def _init_params(self) -> None:
        self.params: dict[str, t.Any] = {}

    def set_params(
        self,
        params: abc.Mapping[str, t.Any] | None = None,
        reset: bool | list[str] = True,
        **kwargs,
    ):
        """Set parameters values.

        Parameters
        ----------
        params:
            Mapping of parameters values.
        reset:
            Passed to :meth:`reset_callback`.
        kwargs:
            Additional parameters. Parameters will be taken in order of first available
            in: ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
        """
        if params is None:
            params = {}
        else:
            params = dict(params)  # shallow copy
        params = params | self.PARAMS_DEFAULTS
        params.update(kwargs)

        self.params.update(params)
        self.reset_callback(reset, params=params)

    def reset_params(self) -> None:
        """Reset parameters to their initial state (empty dict)."""
        self.params = {}


class ParamsSchemePlugin(ParamsPluginAbstract):
    """Parameters are stored in a Scheme object.

    The plugin does not initialize the :attr:`params` attribute. It is set by the first
    call to :meth:`set_params` (which checks if the attribute exists).
    Subsequent calls to :meth:`set_params` will only update the current attribute.

    """

    PARAMS_DEFAULTS: dict[str, t.Any] = {}
    """Default values of parameters or trait instance for new traits.

    Optional. Can be used to define default values for parameters local to a
    data-manager, (*ie* that are not defined in project-wide with
    :mod:`data_assistant.config`).
    """

    RAISE_ON_MISS: bool = False

    def _init_params(self) -> None:
        self.params: Scheme

    def set_params(
        self,
        params: Scheme | None = None,
        reset: bool | list[str] = True,
        **kwargs,
    ):
        """Set parameters values.

        Parameters
        ----------
        params:
            Scheme containing parameters.
            Traits that do not already exist in the current :attr:`params` scheme will
            be added.
        reset:
            Passed to :meth:`reset_callback`.
        kwargs:
            Additional parameters. Parameters will be taken in order of first available
            in: ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
        """
        if params is None:
            params = Scheme()

        params.update(
            self.PARAMS_DEFAULTS,
            allow_new=True,
            raise_on_miss=self.RAISE_ON_MISS,
            **kwargs,
        )

        if not hasattr(self, "params"):
            self.params = params
        else:
            self.params.update(params, allow_new=True, raise_on_miss=self.RAISE_ON_MISS)
        self.reset_callback(reset, params=params)

    def reset_params(self) -> None:
        """Reset parameters to their initial state (not `params` attribute)."""
        del self.params


class _ParamsContext:
    def __init__(self, dm: ParamsPluginAbstract, save_cache: bool):
        self.dm = dm
        self.params = copy.deepcopy(dm.params)
        self.cache: dict | None = None

        if save_cache and isinstance(dm, CachePlugin):
            self.cache = dict(dm.cache)

    def repopulate_cache(self):
        for key, val in self.cache.items():
            # do not overwrite current cache
            if not self.dm.is_cached(key):
                self.dm.set_in_cache(key, val)
                continue

            # check that there is correspondance with saved and current cache
            current_val = self.dm.get_cached(key)
            if current_val != val:
                log.warning(
                    "Different value when restoring cache for key %s, "
                    "saved '%s', has '%s'.",
                    key,
                    str(val),
                    str(current_val),
                )

    def __enter__(self) -> t.Self:
        return self

    def __exit__(self, *exc):
        self.reset_params()
        self.dm.set_params(self.params)

        if self.cache is not None:
            self.repopulate_cache()

        # return false to raise any exception that may have occured
        return False
