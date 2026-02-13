"""Parameters management modules."""

from __future__ import annotations

import logging
import typing as t
from collections import abc

from traitlets import Bunch

from neba.config.application import ApplicationBase
from neba.config.section import Section

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

    def update(self, params: t.Any | None, **kwargs):
        """Update one or more parameters values.

        Other parameters are kept.

        :Not Implemented: Implement in a subclass of this module.
        """
        raise NotImplementedError("Implement in a subclass of this module.")

    def reset(self) -> None:
        """Reset parameters to their initial state (empty dict).

        :Not Implemented: Implement in a subclass of this module.
        """
        raise NotImplementedError("Implement in a subclass of this module.")


_K = t.TypeVar("_K")
_V = t.TypeVar("_V")


class CallbackDict(dict, t.Generic[_K, _V]):
    """Dictionary that sends a callback on change.

    Dictionary is considered flat (setting a nested key will not trigger a callback).
    """

    _callback: abc.Callable[[Bunch], None] | None = None

    def __setitem__(self, k: _K, v: _V):
        old = self.get(k, None)
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
        if params is not None:
            self._params.update(**params)
        self._params.update(**kwargs)

        def handler(change: Bunch):
            self.dm.trigger_callbacks()

        self._params._callback = handler

    def update(self, params: t.Any | None, **kwargs):
        """Update one or more parameters values.

        Other parameters are kept.

        Parameters
        ----------
        params
            Mapping of parameters to set.
        kwargs:
            Other parameters to set (takes precedence over `params`).
        """
        if params is None:
            params = {}
        params.update(kwargs)
        self.params.update(params)

    def reset(self) -> None:
        """Reset parameters to their initial state (empty dict)."""
        self._params.clear()


T_Section = t.TypeVar("T_Section", bound=Section)


class ParamsManagerSectionAbstract(ParamsManagerAbstract[T_Section]):
    """Parameters are stored in a Section object.

    Set and reset methods rely on :meth:`.Section.update` to merge the new parameters
    values to :attr:`params`.
    """

    RAISE_ON_MISS: bool = True
    """Passed to Section.update, If True (default), raise if unkown parameter is passed
    when using set_params."""

    _params: T_Section

    def _setup_cache_callback(self) -> None:
        # add callbacks to void the cache

        def handler(change: Bunch):
            self.dm.trigger_callbacks()

        for subsection in self._params.subsections_recursive():
            subsection.observe(handler)

    def update(
        self,
        params: Section | abc.Mapping[str, t.Any] | None = None,
        **kwargs,
    ):
        """Update one or more parameters values.

        New traits can be added if :attr:`RAISE_ON_MISS` is False. If given via Section,
        new traits will take their current value. If given via a
        :class:`~traitlets.TraitType` instance (in a mapping), new traits will take
        their default value.

        Parameters
        ----------
        params:
            Section or mapping to use as parameters.
        kwargs:
            Other parameters values.
        """
        if params is None:
            params = {}

        self._params.update(
            params, allow_new=True, raise_on_miss=self.RAISE_ON_MISS, **kwargs
        )

    def reset(self) -> None:
        """Reset section to its default values."""
        self._params.reset()


class ParamsManagerSection(ParamsManagerSectionAbstract[T_Section]):
    """Parameters are stored in a Section object.

    Set and update methods rely on :meth:`.Section.update` to merge the new parameters
    values to :attr:`params`.
    """

    SECTION_CLS: type[T_Section] = Section  # type: ignore[assignment]
    """Section class to use as parameters."""

    _params: T_Section

    @classmethod
    def new(cls, section: type[T_Section]) -> type[ParamsManagerSection[T_Section]]:
        """Return a subclass with the SECTION_CLS attribute set."""
        return type("ParamsManagerSectionDynamic", (cls,), {"SECTION_CLS": section})

    def __init__(self, params: T_Section | None = None, **kwargs):
        self._params = self.SECTION_CLS()
        self._params.update(params, **kwargs)
        self._setup_cache_callback()


T_App = t.TypeVar("T_App", bound=ApplicationBase)


class ParamsManagerApp(ParamsManagerSectionAbstract[T_App]):
    """Parameters are retrieved from an application instance."""

    def __init__(self, params: T_App, **kwargs):
        if not isinstance(params, ApplicationBase):
            raise TypeError(
                f"An application must be passed as parameter, received {type(params)}."
            )
        self._params = params.copy()
        self._params.update(**kwargs)
        self._setup_cache_callback()
