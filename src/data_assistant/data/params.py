"""Parameters management plugins."""

from __future__ import annotations

import logging
import typing as t
from collections import abc

from ..config.section import Section
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


T_Section = t.TypeVar("T_Section", bound=Section)


class ParamsManagerSectionAbstract(ParamsManagerAbstract[T_Section]):
    """Parameters are stored in a Section object.

    Set and update methods rely on :meth:`.Section.update` to merge the new parameters
    values to :attr:`params`.
    """

    RAISE_ON_MISS: bool = True

    _params: T_Section

    def set_params(
        self,
        params: Section | abc.Mapping[str, t.Any] | None = None,
        **kwargs,
    ):
        """Set parameters values.

        Parameters
        ----------
        params:
            Section to use as parameters. If :attr:`PARAMS_PATH` is not None, it will be
            used to obtain a sub-section to use. If None, the default section class
            (:attr:`SECTION`) will be used (with :attr:`PARAMS_DEFAULTS` added). Traits
            that do not already exist in the :attr:`params` section will be added.
        kwargs:
            Other parameters values in the form ``name=value``. The value can be
            a :class:`~traitlets.TraitType` instance in which case it will be added
            to the parameters section with its default value.
        """
        self._reset_params()
        self.update_params(params, **kwargs)

    def update_params(
        self,
        params: Section | abc.Mapping[str, t.Any] | None = None,
        **kwargs,
    ):
        """Update one or more parameters values.

        Other parameters are kept.

        Parameters
        ----------
        params:
            Section to add values to current parameters. Same as for :meth:`set_params`.
        kwargs:
            Other parameters values in the form ``name=value``. The value can be
            a :class:`~traitlets.TraitType` instance in which case it will be added
            to the parameters section with its default value.
        """
        if params is None:
            params = {}

        self._params.update(
            params, allow_new=True, raise_on_miss=self.RAISE_ON_MISS, **kwargs
        )

    def _reset_params(self) -> None:
        self._params.reset()


class ParamsManagerSection(ParamsManagerSectionAbstract[T_Section]):
    """Parameters are stored in a Section object.

    Set and update methods rely on :meth:`.Section.update` to merge the new parameters
    values to :attr:`params`.
    """

    SECTION_CLS: type[T_Section] = Section  # type: ignore[assignment]
    """Section class to use as parameters."""

    _params: T_Section

    def _init_module(self) -> None:
        self._params = self.SECTION_CLS()


class ParamsManagerApp(ParamsManagerSectionAbstract[T_Section]):
    def _init_module(self) -> None:
        app_cls = self.dm._application_cls
        if app_cls is None:
            raise TypeError(
                "ParamsManagerApp requires the application type to be set "
                "on the data manager. Use @Application.register_section."
            )
        self._params = app_cls.instance().copy()
