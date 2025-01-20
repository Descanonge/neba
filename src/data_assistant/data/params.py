"""Parameters management plugins."""

from __future__ import annotations

import logging
import typing as t
from collections import abc

from ..config.scheme import Scheme
from .module import Module
from .util import T_Params

log = logging.getLogger(__name__)


class ParamsManagerAbstract(t.Generic[T_Params], Module):
    """Abstract Module for parameters management."""

    PARAMS_DEFAULTS: abc.Mapping[str, t.Any] = {}
    """Default values of parameters.

    Optional. Can be used to define default values for parameters local to a
    data-manager, (*ie* that are not defined in project-wide with
    :mod:`data_assistant.config`).
    """

    _params: T_Params

    @property
    def params(self) -> T_Params:
        """Parameters currently stored."""
        return self._params

    def set_params(self, params=None, **kwargs):
        """Set parameters values.

        :Not Implemented: Implement in a subclass of this module.
        """
        raise NotImplementedError("Implement in a subclass of this module.")

    def update_params(self, params: t.Any | None, **kwargs):
        """Update one or more parameters values.

        Other parameters are kept.

        :Not Implemented: Implement in a subclass of this module.
        """
        raise NotImplementedError("Implement in a subclass of this module.")

    def _reset_params(self) -> None:
        """Reset parameters to their initial state (empty dict).

        :Not Implemented: Implement in a subclass of this module.
        """
        raise NotImplementedError("Implement in a subclass of this module.")


class ParamsManager(ParamsManagerAbstract[dict[str, t.Any]]):
    """Parameters stored in a dictionnary."""

    def _init_module(self) -> None:
        self._params = {}

    def set_params(self, params: abc.Mapping[str, t.Any] | None = None, **kwargs):
        """Set parameters values.

        Parameters
        ----------
        params:
            Mapping of parameters values.
        kwargs:
            Additional parameters. Parameters will be taken in order of first available
            in: ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
        """
        self._reset_params()
        self.update_params(params, **kwargs)

    def update_params(self, params: t.Any | None, **kwargs):
        """Update one or more parameters values.

        Other parameters are kept.

        Parameters
        ----------
        kwargs:
            Other parameters values in the form ``name=value``.
        """
        if params is None:
            params = {}
        params.update(kwargs)
        self.params.update(params)

    def _reset_params(self) -> None:
        """Reset parameters to their initial state (empty dict)."""
        self._params = {}


T_Scheme = t.TypeVar("T_Scheme", bound=Scheme)


class ParamsManagerScheme(ParamsManagerAbstract[T_Scheme]):
    """Parameters are stored in a Scheme object.

    Set and update methods rely on :meth:`.Scheme.update` to merge the new parameters
    values to :attr:`params`.
    """

    PARAMS_DEFAULTS: dict[str, t.Any] = {}
    """Default values of new traits.

    Optional. Can be used to define default values for parameters local to a
    data-manager, (*ie* that are not defined in project-wide with
    :mod:`data_assistant.config`).

    TODO Explain how to add traits.
    """

    RAISE_ON_MISS: bool = True

    PARAMS_PATH: str | None = None
    """Path (dot-separated keys) that lead to the subscheme containing parameters."""

    # Fix ignore with default kwarg in TypeVar in python3.13
    SCHEME: type[T_Scheme] = Scheme  # type: ignore
    """Scheme class to use as parameters.

    This is *after* following :attr:`.PARAMS_PATH` on an input argument.
    """

    _params: T_Scheme

    def _init_module(self) -> None:
        self._reset_params()

    def set_params(
        self,
        params: Scheme | abc.Mapping[str, t.Any] | None = None,
        **kwargs,
    ):
        """Set parameters values.

        Parameters
        ----------
        params:
            Scheme to use as parameters. If :attr:`PARAMS_PATH` is not None, it will be
            used to obtain a sub-scheme to use. If None, the default scheme class
            (:attr:`SCHEME`) will be used (with :attr:`PARAMS_DEFAULTS` added). Traits
            that do not already exist in the :attr:`params` scheme will be added.
        kwargs:
            Other parameters values in the form ``name=value``. The value can be
            a :class:`~traitlets.TraitType` instance in which case it will be added
            to the parameters scheme with its default value.
        """
        self._reset_params()
        self.update_params(params, **kwargs)

    def update_params(
        self,
        params: Scheme | abc.Mapping[str, t.Any] | None = None,
        **kwargs,
    ):
        """Update one or more parameters values.

        Other parameters are kept.

        Parameters
        ----------
        params:
            Scheme to add values to current parameters. Same as for :meth:`set_params`.
        kwargs:
            Other parameters values in the form ``name=value``. The value can be
            a :class:`~traitlets.TraitType` instance in which case it will be added
            to the parameters scheme with its default value.
        """
        if params is None:
            params = {}
        # Select subscheme
        elif isinstance(params, Scheme) and self.PARAMS_PATH is not None:
            params = params[self.PARAMS_PATH]
            if not isinstance(params, Scheme):
                raise TypeError(f"'{self.PARAMS_PATH}' did not led to subscheme.")

        self._params.update(
            params, allow_new=True, raise_on_miss=self.RAISE_ON_MISS, **kwargs
        )

    def _reset_params(self) -> None:
        self._params = self.SCHEME()
        self._params.update(
            self.PARAMS_DEFAULTS, allow_new=True, raise_on_miss=self.RAISE_ON_MISS
        )
