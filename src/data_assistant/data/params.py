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

    RAISE_ON_MISS: bool = True

    SCHEME_CLS: type[T_Scheme]
    """Scheme class to use as parameters."""

    _params: T_Scheme

    def _init_module(self) -> None:
        if not hasattr(self, "SCHEME_CLS"):
            app = self.dm._application_cls
            self.SCHEME_CLS = app if app is not None else Scheme  # type: ignore[assignment]

        self._params = self.SCHEME_CLS()

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

        self._params.update(
            params, allow_new=True, raise_on_miss=self.RAISE_ON_MISS, **kwargs
        )

    def _reset_params(self) -> None:
        self._params.reset()
