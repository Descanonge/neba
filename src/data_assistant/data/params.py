"""Parameters management plugins."""

from __future__ import annotations

import logging
import typing as t
from collections import abc

from traitlets import Bunch

from data_assistant.config.application import ApplicationBase
from data_assistant.config.section import Section

from .module import Module
from .util import T_Params

log = logging.getLogger(__name__)


class ParamsManagerAbstract(t.Generic[T_Params], Module):
    """Abstract Module for parameters management."""

    _allow_instantiation_failure = False

    PARAMS_DEFAULTS: abc.Mapping[str, t.Any] = {}
    """Default values of parameters."""

    _params: T_Params

    @property
    def params(self) -> T_Params:
        """Parameters currently stored."""
        return self._params

    def set_params(self, params: t.Any | None, **kwargs):
        """Update one or more parameters values.

        Other parameters are kept.

        :Not Implemented: Implement in a subclass of this module.
        """
        raise NotImplementedError("Implement in a subclass of this module.")

    def reset_params(self, params=None, **kwargs):
        """Reset parameters values.

        :Not Implemented: Implement in a subclass of this module.
        """
        raise NotImplementedError("Implement in a subclass of this module.")

    def _reset_params(self) -> None:
        """Reset parameters to their initial state (empty dict).

        :Not Implemented: Implement in a subclass of this module.
        """
        raise NotImplementedError("Implement in a subclass of this module.")


_K = t.TypeVar("_K")
_V = t.TypeVar("_V")


class CallbackDict(dict, t.Generic[_K, _V]):
    """Dictionary that sends a callback on change.

    Dictionary is considered flat (setting a nested key will not trigger a callback).

    :Untested:
    """

    _callback: abc.Callable[[Bunch], None] | None = None

    def __setitem__(self, k: _K, v: _V):
        old = self[k]
        super().__setitem__(k, v)
        if self._callback is None:
            return

        # lifted from traitlets.HasTraits.set
        try:
            silent = bool(old == v)
        except Exception:
            # if there is an error in comparing, default to notify
            silent = False
        if silent is not True:
            # we explicitly compare silent to True just in case the equality
            # comparison above returns something other than True/False
            self._callback(Bunch(name=k, old=old, new=v, type="change"))


class ParamsManagerDict(ParamsManagerAbstract[CallbackDict[str, t.Any]]):
    """Parameters stored in a dictionnary."""

    def __init__(self, params: abc.Mapping[str, t.Any] | None = None, **kwargs):
        self._params = CallbackDict()
        self._params.update(**kwargs)

        def handler(change: Bunch):
            self.dm.reset()

        self._params._callback = handler

    def set_params(self, params: t.Any | None, **kwargs):
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

    def reset_params(self, params: abc.Mapping[str, t.Any] | None = None, **kwargs):
        """Reset parameters values.

        Parameters
        ----------
        params:
            Mapping of parameters values.
        kwargs:
            Additional parameters. Parameters will be taken in order of first available
            in: ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
        """
        self._reset_params()
        self.set_params(params, **kwargs)

    def _reset_params(self) -> None:
        """Reset parameters to their initial state (empty dict)."""
        self._params.clear()


T_Section = t.TypeVar("T_Section", bound=Section)


class ParamsManagerSectionAbstract(ParamsManagerAbstract[T_Section]):
    """Parameters are stored in a Section object.

    Set and reset methods rely on :meth:`.Section.update` to merge the new parameters
    values to :attr:`params`.
    """

    RAISE_ON_MISS: bool = True

    _params: T_Section

    def _setup_cache_callback(self):
        # add callbacks to void the cache

        def handler(change: Bunch):
            self.dm.reset()

        for subsection in self._params._subsections_recursive():
            subsection.observe(handler)

    def set_params(
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

    def reset_params(
        self,
        params: Section | abc.Mapping[str, t.Any] | None = None,
        **kwargs,
    ):
        """Reset parameters values.

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
        self.set_params(params, **kwargs)

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

    def __init__(self, params: T_Section | None = None, **kwargs):
        self._params = self.SECTION_CLS()
        self._params.update(params, **kwargs)
        self._setup_cache_callback()


T_App = t.TypeVar("T_App", bound=ApplicationBase)


class ParamsManagerApp(ParamsManagerSectionAbstract[T_App]):
    """Parameters are retrieved from an application instance."""

    def __init__(self, params: T_App, **kwargs):
        if params is None:
            raise TypeError("An application must be passed as parameter.")
        self._params = params.copy()
        self._params.update(**kwargs)
        self._setup_cache_callback()
