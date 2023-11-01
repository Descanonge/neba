
from __future__ import annotations

from collections.abc import Iterator, Hashable
from typing import Any, Callable

from traitlets import Instance, TraitType
from traitlets.config import Configurable, Config


class Scheme(Configurable):
    """Configuration specification.

    A Configurable object facilitating nested Configurables.
    All traits are automatically tagged as configurable (``.tag(config=True)``),
    unless already tagged.
    Any class attribute that is a subclass of Scheme will be registered as a
    nested subscheme and replaced by a :class:`traitlets.Instance` trait.
    """

    _subschemes: dict[str, type[Scheme]]
    """Mapping of nested Configurables classes."""

    def __init_subclass__(cls, /, **kwargs):
        """Subclass initialization hook.

        Any subclass will automatically run this after being defined.

        Register subschemes and tag all traits as configurable (unless already
        tagged).

        It will then run the ``setup_class`` class method to trigger the
        initialization process of traitlets
        (:func:`traitlets.MetaHasTraits.class_setup`).
        """
        super().__init_subclass__(**kwargs)

        cls._subschemes = {}
        classdict = cls.__dict__
        for k, v in classdict.items():
            # tag traits as configurable
            if isinstance(v, TraitType):
                if v.metadata.get('config', True):
                    v.tag(config=True)

            # register nested schemes
            if isinstance(v, type) and issubclass(v, Scheme):
                cls._subschemes[k] = v
                setattr(cls, k,
                        Instance(v, args=(), kw={}))

        cls.setup_class(classdict)

    def instanciate_subschemes(self):
        """Recursively instanciate subschemes traits."""
        for k, subscheme in self._subschemes.items():
            self.set_trait(k, subscheme(parent=self))
            getattr(self, k).init_subschemes()

    @classmethod
    def class_traits_recursive(cls) -> dict:
        """Return nested/recursive dict of all traits."""
        config = dict()
        config.update(cls.class_own_traits(config=True))
        for name, subscheme in cls._subschemes.items():
            config[name] = subscheme.class_traits_recursive()
        return config

    @classmethod
    def _subschemes_recursive(cls) -> Iterator[type[Scheme]]:
        """Iterate recursively over all subschemes."""
        for subscheme in cls._subschemes.values():
            yield from subscheme._subschemes_recursive()
        yield cls


def remap(config: dict, func: Callable[[dict, Hashable, Any, list[Hashable]], None]):
    """Recursively apply function to Config keys.

    Parameters
    ----------
    config:
        Dictionnary to apply function to.
    func:
        Function to apply. Must take as argument: a dictionnary (not necessarily
        the full ``config``, can be a nested level), the current key, the current
        value, and the current path (the list of keys used to obtain the current
        dictionnary).

        It needs not return any value. It should directly act on the
        dictionnary.
    """
    _remap(config, func, [])

def _remap(config, func, path: list[str]):
    for k, v in config.items():
        if isinstance(v, dict):
            _remap(v, func, path + [k])
        else:
            func(config, k, v, path)
