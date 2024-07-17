"""Parameters management plugins."""

from __future__ import annotations

import logging
import typing as t
from collections import abc

from ..config.scheme import Scheme
from .plugin import Plugin

log = logging.getLogger(__name__)


class ParamsMappingPlugin(Plugin):
    """Parameters are stored in a dictionary."""

    PARAMS_DEFAULTS: dict[str, t.Any] = {}

    def _init_plugin(self) -> None:
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
        self._reset_params()
        self.update_params(params, reset=reset, **kwargs)

    def update_params(
        self, params: t.Any | None, reset: bool | list[str] = True, **kwargs
    ):
        """Update one or more parameters values.

        Other parameters are kept.

        Parameters
        ----------
        reset:
            Passed to :meth:`reset_callback`.
        kwargs:
            Other parameters values in the form ``name=value``.
        """
        if params is None:
            params = {}
        else:
            params = dict(params)  # shallow copy
        params = params | self.PARAMS_DEFAULTS
        params.update(kwargs)

        self.params.update(params)
        self.reset_callback(reset, params=params)

    def _reset_params(self) -> None:
        """Reset parameters to their initial state (empty dict)."""
        self.params = {}

    @property
    def params_as_dict(self) -> dict[str, t.Any]:
        """Return the parameters as a dictionary."""
        return self.params


class ParamsSchemePlugin(Plugin):
    """Parameters are stored in a Scheme object.

    Set and update methods rely on :meth:`.Scheme.update` to merge the new parameters
    values to :attr:`params`.
    """

    PARAMS_DEFAULTS: dict[str, t.Any] = {}
    """Default values of new traits.

    Optional. Can be used to define default values for parameters local to a
    data-manager, (*ie* that are not defined in project-wide with
    :mod:`data_assistant.config`).
    """

    RAISE_ON_MISS: bool = False

    PARAMS_PATH: str | None = None
    """Path (dot-separated keys) that lead to the subscheme containing parameters."""

    SCHEME: type[Scheme] = Scheme
    """Scheme class to use as parameters.

    This is *after* following :attr:`.PARAMS_PATH` on an input argument.
    """

    def _init_plugin(self) -> None:
        self._reset_params()

    def set_params(
        self, params: Scheme | None = None, reset: bool | list[str] = True, **kwargs
    ):
        """Set parameters values.

        Parameters
        ----------
        params:
            Scheme to use as parameters. If :attr:`PARAMS_PATH` is not None, it will be
            used to obtain a sub-scheme to use. If None, the default scheme class
            (:attr:`SCHEME`) will be used (with :attr:`PARAMS_DEFAULTS` added). Traits
            that do not already exist in the :attr:`params` scheme will be added.
        reset:
            Passed to :meth:`reset_callback`.
        kwargs:
            Other parameters values in the form ``name=value``. The value can be
            a :class:`~traitlets.TraitType` instance in which case it will be added
            to the parameters scheme with its default value.
        """
        self._reset_params()
        self.update_params(params, reset=reset, **kwargs)
        self.reset_callback(reset, params=params)

    def update_params(
        self, params: Scheme | None, reset: bool | list[str] = True, **kwargs
    ):
        """Update one or more parameters values.

        Other parameters are kept.

        Parameters
        ----------
        params:
            Scheme to add values to current parameters. Same as for :meth:`set_params`.
        reset:
            Passed to :meth:`reset_callback`.
        kwargs:
            Other parameters values in the form ``name=value``. The value can be
            a :class:`~traitlets.TraitType` instance in which case it will be added
            to the parameters scheme with its default value.
        """
        if params is None:
            params = Scheme()
        # Select subscheme
        elif self.PARAMS_PATH is not None:
            params = params[self.PARAMS_PATH]
            if not isinstance(params, Scheme):
                raise TypeError(f"'{self.PARAMS_PATH}' did not led to subscheme.")

        self.params.update(
            params, allow_new=True, raise_on_miss=self.RAISE_ON_MISS, **kwargs
        )
        self.reset_callback(reset, params=params)

    def _reset_params(self) -> None:
        self.params = self.SCHEME()
        self.params.update(
            self.PARAMS_DEFAULTS, allow_new=True, raise_on_miss=self.RAISE_ON_MISS
        )

    @property
    def params_as_dict(self) -> dict[str, t.Any]:
        """Return the parameters as a dictionary."""
        return dict(self.params)
