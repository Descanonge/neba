"""Parameters management modules."""

from __future__ import annotations

import logging
import typing as t
from collections import abc

from traitlets import Bunch, TraitType

from neba.config.application import Application
from neba.config.section import Section

from .module import Module
from .types import T_Params

log = logging.getLogger(__name__)


class ParametersAbstract(t.Generic[T_Params], Module):
    """Abstract Module for parameters management."""

    _allow_instantiation_failure = False

    _params: T_Params

    @property
    def direct(self) -> T_Params:
        """Direct access to parameters container."""
        return self._params

    def __getitem__(self, key: str) -> t.Any:
        raise NotImplementedError("Implement in a subclass of this module.")

    def __setitem__(self, key: str, value: t.Any):
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        raise NotImplementedError("Implement in a subclass of this module.")

    def get(self, key: str, default: t.Any = None) -> t.Any:
        """Return a parameter value.

        :Not Implemented: Implement in a subclass of this module.

        Parameters
        ----------
        key
            Name of the parameter to retrieve.
        default
            If not None, return this value if the parameters is not found.
        """
        raise NotImplementedError("Implement in a subclass of this module.")

    def set(self, key: str, value: t.Any):
        """Set a parameter to value.

        :Not Implemented: Implement in a subclass of this module.
        """
        raise NotImplementedError("Implement in a subclass of this module.")

    def update(self, params: t.Any | None = None, **kwargs):
        """Update one or more parameters values.

        :Not Implemented: Implement in a subclass of this module.

        Parameters
        ----------
        params
            Mapping of parameters to set.
        kwargs:
            Other parameters to set (takes precedence over `params`).
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


class ParametersDict(ParametersAbstract[CallbackDict[str, t.Any]]):
    """Parameters stored in a dictionnary."""

    def __init__(self, params: abc.Mapping[str, t.Any] | None = None, **kwargs):
        self._params = CallbackDict()
        if params is not None:
            self._params.update(**params)
        self._params.update(**kwargs)

        def handler(change: Bunch):
            self.di.trigger_callbacks()

        self._params._callback = handler

    def __getitem__(self, key: str) -> t.Any:
        return self._params[key]

    def __contains__(self, key: str) -> bool:
        return key in self._params

    def get(self, key: str, default: t.Any = None) -> t.Any:
        """Return a parameter value.

        Parameters
        ----------
        key
            Name of the parameter to retrieve.
        default
            Return this value if the parameters is not found.
        """
        return self._params.get(key, default)

    def set(self, key: str, value: t.Any):
        """Set a parameter to value."""
        dict.__setitem__(self._params, key, value)
        self.di.trigger_callbacks()

    def update(self, params: t.Any | None = None, **kwargs):
        """Update one or more parameters values.

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
        self._params.update(params)
        self.di.trigger_callbacks()

    def reset(self) -> None:
        """Reset parameters to their initial state (empty dict)."""
        self._params.clear()
        self.di.trigger_callbacks()


T_Section = t.TypeVar("T_Section", bound=Section)


class ParametersSectionBase(ParametersAbstract[T_Section]):
    """Parameters are stored in a Section object.

    Set and reset methods rely on :meth:`.Section.update` to merge the new parameters
    values to :attr:`params`.
    """

    allow_new: bool = True
    """If True (default), allow to create new traits when using :meth:`update` and
    :meth:`set`."""

    _params: T_Section

    def _setup_cache_callback(self) -> None:
        # add callbacks to void the cache

        def handler(change: Bunch):
            self.di.trigger_callbacks()

        for subsection in self._params.subsections_recursive():
            subsection.observe(handler)

    def __getitem__(self, key: str) -> t.Any:
        return self._params[key]

    def __contains__(self, key: str) -> bool:
        return key in self._params

    def get(self, key: str, default: t.Any = None) -> t.Any:
        """Return a parameter value.

        Parameters
        ----------
        key
            Name of the parameter to retrieve.
        default
            Return this value if the parameters is not found.
        """
        return self._params.get(key, default)

    def set(self, key: str, value: t.Any):
        """Set a parameter to value.

        :param value: Value to set. If :attr:`allow_new` is True, can be a
            :class:`traitlets.TraitType` to add to parameters.
        """
        if self.allow_new and isinstance(value, TraitType) and key not in self._params:
            self._params.add_trait(key, value)
        else:
            self._params.__setitem__(key, value)
        self.di.trigger_callbacks()

    def update(self, params: t.Any | None = None, **kwargs):
        """Update one or more parameters values.

        Parameters
        ----------
        params
            Mapping of parameters to set.
        kwargs:
            Other parameters to set (takes precedence over `params`).
        """
        self._params.update(params, allow_new=self.allow_new, **kwargs)
        self.di.trigger_callbacks()

    def reset(self) -> None:
        """Reset section to its default values."""
        self._params.reset()
        self.di.trigger_callbacks()


class ParametersSection(ParametersSectionBase[T_Section]):
    """Parameters are stored in a Section object.

    Set and update methods rely on :meth:`.Section.update` to merge the new parameters
    values to :attr:`params`.
    """

    SECTION_CLS: type[T_Section] = Section  # type: ignore[assignment]
    """Section class to use as parameters."""

    _params: T_Section

    @classmethod
    def new(cls, section: type[T_Section]) -> type[ParametersSection[T_Section]]:
        """Return a subclass with the SECTION_CLS attribute set."""
        return type("ParametersSectionDynamic", (cls,), {"SECTION_CLS": section})

    def __init__(self, params: T_Section | None = None, **kwargs):
        self._params = self.SECTION_CLS()
        self._params.update(params, **kwargs)
        self._setup_cache_callback()


T_App = t.TypeVar("T_App", bound=Application)


class ParametersApp(ParametersSectionBase[T_App]):
    """Parameters are retrieved from an application instance."""

    def __init__(self, params: T_App, **kwargs):
        if not isinstance(params, Application):
            raise TypeError(
                f"An application must be passed as parameter, received {type(params)}."
            )
        self._params = params.copy()
        self._params.update(**kwargs)
        self._setup_cache_callback()
