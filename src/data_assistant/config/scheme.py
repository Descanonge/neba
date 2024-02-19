from __future__ import annotations

from collections.abc import Callable, Generator, Hashable, Iterator
from inspect import Parameter, signature
from typing import Any

from traitlets import Bool, Instance, List, TraitType, Unicode, Union
from traitlets.config import Configurable

from .loader import ConfigValue


class FixableTrait(Union):
    """Fixable parameter, specified in a filename pattern.

    A fixable parameter (ie specified in a filename pattern) can take:
    * a value of the appropriate type (int, float, bool, or str depending on the format),
    * a string (then the filename part must match that string, which
    can be a regular expression),
    * a list of values (see 1) or strings (see 2), (then any value of
    the list will be accepted in the filenames).

    Parameters
    ----------
    trait
        The trait corresponding to the fixable parameter format. Some properties are
        kept: ``default_value``, ``allow_none``, ``help``. The metadata is not kept.
    kwargs
        Arguments passed to the Union trait created.
    """

    info_text = "a fixable"

    def __init__(self, trait: TraitType, **kwargs) -> None:
        self.trait = trait
        traits = [
            trait,
            Unicode(),
            List([Union([trait, Unicode()])]),
        ]
        for arg in ["default_value", "help", "allow_none"]:
            value = getattr(trait, arg, None)
            if value is not None:
                kwargs.setdefault(arg, value)
        super().__init__(traits, **kwargs)

    # def from_string()
    #     # manage int ranges ?


def subscheme(scheme: type[Scheme]) -> Instance:
    """Transform a subscheme into a proper trait.

    This is done automatically even without this function, but it can help static
    type checkers.
    """
    return Instance(scheme, args=(), kwargs={}).tag(subscheme=True)


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

    _attr_completion_only_traits = Bool(
        False, help="Only keep configurable traits in attribute completion."
    )

    aliases: dict[str, str] = {}

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
        cls._setup_scheme()

    @classmethod
    def _setup_scheme(cls):
        cls._subschemes = {}
        classdict = cls.__dict__
        for k, v in classdict.items():
            # tag traits as configurable
            if isinstance(v, TraitType):
                if v.metadata.get("config", True):
                    v.tag(config=True)

            # transform subschemes in traits
            if isinstance(v, type) and issubclass(v, Scheme):
                setattr(cls, k, subscheme(v))

        for k, v in classdict.items():
            # register subschemes
            if isinstance(v, Instance) and issubclass(v.klass, Scheme):
                cls._subschemes[k] = v.klass

        cls.setup_class(classdict)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.postinit()

    def postinit(self):
        pass

    def __str__(self) -> str:
        lines = [f"{self.__class__.__name__}:"]
        for key, trait in self.traits(config=True).items():
            if key in self._subschemes:
                continue
            trait_cls = trait.__class__.__name__
            value = trait.get(self)
            default = trait.default()
            lines.append(f"  -{key} ({trait_cls}): {value} [default: {default}]")

        # TODO: add Enum

        if self._subschemes:
            lines.append(
                "subschemes: {}".format(
                    ", ".join(
                        [
                            f"{k} ({subscheme.__name__})"
                            for k, subscheme in self._subschemes.items()
                        ]
                    )
                )
            )
        return "\n".join(lines)

    def __repr__(self) -> str:
        return str(self)

    def __dir__(self):
        if not self._attr_completion_only_traits:
            return super().__dir__()
        configurables = set(self.trait_names(config=True))
        subschemes = set(self._subschemes.keys())
        return configurables | subschemes

    @classmethod
    def _subschemes_recursive(cls) -> Iterator[type[Scheme]]:
        """Iterate recursively over all subschemes."""
        for subscheme in cls._subschemes.values():
            yield from subscheme._subschemes_recursive()
        yield cls

    @classmethod
    def class_traits_recursive(cls) -> dict:
        """Return nested/recursive dict of all traits."""
        config: dict[Any, Any] = dict()
        config.update(cls.class_own_traits(config=True))
        for name, subscheme in cls._subschemes.items():
            config[name] = subscheme.class_traits_recursive()
        return config

    # Lifted from traitlets.config.application.Application
    @classmethod
    def _classes_inc_parents(
        cls, classes: list[type[Scheme]] | None = None
    ) -> Generator[type[Configurable], None, None]:
        """Iterate through configurable classes, including configurable parents.

        :param classes:
            The list of classes to iterate; if not set, uses subschemes.

        Children should always be after parents, and each class should only be
        yielded once.
        """
        if classes is None:
            classes = list(cls._subschemes_recursive())

        seen = set()
        for c in classes:
            # We want to sort parents before children, so we reverse the MRO
            for parent in reversed(c.mro()):
                if issubclass(parent, Configurable) and (parent not in seen):
                    seen.add(parent)
                    yield parent

    def instanciate_subschemes(self, config: dict[str, Any]):
        """Recursively instanciate subschemes."""
        for name, subscheme in self._subschemes.items():
            subconf = config.get(name, {})
            # discard subsubconfs using the scheme
            kwargs = {
                t: subconf[t]
                for t in subscheme.class_trait_names(subscheme=None)
                if t in subconf
            }
            # Transform from ConfigValue to a value
            for key, val in kwargs.items():
                kwargs[key] = val.get_value()
            # set trait to a new instance
            self.set_trait(name, subscheme(parent=self, **kwargs))
            # recursive on this new instance
            getattr(self, name).instanciate_subschemes(subconf)

    def remap(
        self,
        func: Callable[[Configurable, dict, Hashable, TraitType, list[str]], None],
        **metadata,
    ) -> dict[Hashable, Any]:
        """Recursively apply function to traits.

        Parameters
        ----------
        func:
            Function to apply. Must take as argument: the current configurable,
            a dictionnary of traits for the current configurable, the current
            trait name, the current trait, and the current path (the list of
            keys used to get to this configurable).

            It needs not return any value. It should directly act on the
            dictionnary.
        metadata:
            Select traits.
        """

        def recurse(scheme: Scheme, outsec: dict, path: list[str]):
            for name, trait in outsec.items():
                newpath = path + [name]
                if name in scheme._subschemes:
                    subscheme = getattr(scheme, name)
                    recurse(subscheme, outsec[name], newpath)
                else:
                    func(scheme, outsec, name, trait, newpath)

        output = self.traits_recursive(**metadata)
        recurse(self, output, [])
        return output

    def traits_recursive(self, **metadata) -> dict:
        """Return nested dictionnary of traits."""
        traits = dict()
        for name, trait in self.traits(**metadata, subscheme=None).items():
            traits[name] = trait
        for name in self._subschemes:
            traits[name] = getattr(self, name).traits_recursive(**metadata)
        return traits

    def defaults_recursive(self, config=True, **metadata):
        """Return nested dictionnary of default traits values."""

        def f(configurable, output, key, trait, path):
            output[key] = trait.default()

        output = self.remap(f, config=config, **metadata)
        return output

    def values_recursive(self, config=True, **metadata):
        """Return nested dictionnary of traits values."""

        def f(configurable, output, key, trait, path):
            output[key] = trait.get(configurable)

        output = self.remap(f, config=config, **metadata)
        return output

    def values(self, select: list[str] | None = None) -> dict:
        """Return selection of parameters.

        Only direct traits. Subschemes are ignored.
        """
        # get configurable, not subscheme traits
        values = self.trait_values(config=True, subscheme=None)

        # restrict to selection
        if select is not None:
            values = {k: v for k, v in values.items() if k in select}
        return values

    @classmethod
    def class_resolve_key(
        cls, key: str | list[str]
    ) -> tuple[str, type[Scheme], TraitType | None]:
        if isinstance(key, str):
            key = key.split(".")

        *prefix, lastname = key
        fullkey = []
        subscheme = cls
        for subkey in prefix:
            if subkey in subscheme._subschemes:
                subscheme = subscheme._subschemes[subkey]
                fullkey.append(subkey)
            elif subkey in cls.aliases:
                alias = cls.aliases[subkey].split(".")
                fullkey += alias
                for alias_subkey in alias:
                    subscheme = subscheme._subschemes[alias_subkey]
            else:
                raise KeyError(f"No subscheme '{subkey}' in class {subscheme}")

        trait = getattr(subscheme, lastname)

        return ".".join(fullkey + [lastname]), subscheme, trait

    def resolve_key(self, key: str | list[str]) -> tuple[str, Scheme, TraitType | None]:
        if isinstance(key, str):
            key = key.split(".")

        *prefix, lastname = key
        fullkey = []
        subscheme = self
        for subkey in prefix:
            if subkey in subscheme._subschemes:
                subscheme = getattr(subscheme, subkey)
                fullkey.append(subkey)
            elif subkey in self.aliases:
                alias = self.aliases[subkey].split(".")
                fullkey += alias
                for alias_subkey in alias:
                    subscheme = getattr(subscheme, alias_subkey)
            else:
                raise KeyError(f"No subscheme '{subkey}' in class {subscheme}")

        trait = subscheme.traits()[lastname]

        return ".".join(fullkey + [lastname]), subscheme, trait

    @classmethod
    def resolve_class_key(cls, key: str | list[str]) -> list[str]:
        if isinstance(key, str):
            key = key.split(".")
        if len(key) > 2:
            raise KeyError(
                f"A parameter --Class.trait cannot be nested ({'.'.join(key)})."
            )

        clsname, traitname = key

        def recurse(scheme: type[Scheme], fullpath: list[str]) -> Iterator[str]:
            for name, subscheme in scheme._subschemes.items():
                newpath = fullpath + [name]
                if subscheme.__name__ == clsname:
                    yield ".".join(newpath + [traitname])
                yield from recurse(subscheme, newpath)

        return list(recurse(cls, []))

    @classmethod
    def resolve_config(cls, config: dict[str, ConfigValue]) -> dict[str, ConfigValue]:
        config_classes = [cls.__name__ for cls in cls._classes_inc_parents()]

        # Transform Class.trait keys into fullkeys
        no_class_key: dict[str, ConfigValue] = {}
        for key, val in config.items():
            # Set the priority of class traits lower and duplicate them
            # for each instance of their class in the config tree
            if key.split(".")[0] in config_classes:
                val.priority = 100
                for fullkey in cls.resolve_class_key(key):
                    no_class_key[fullkey] = val.copy(key=fullkey)
            else:
                no_class_key[key] = val

        # Resolve fullpath for all keys
        output = {}
        for key, val in no_class_key.items():
            fullkey, container_cls, trait = cls.class_resolve_key(key)
            val.container_cls = container_cls
            val.trait = trait
            output[fullkey] = val

        return output

    @classmethod
    def merge_configs(
        cls,
        *configs: dict[str, ConfigValue],
    ) -> dict[str, ConfigValue]:
        out: dict[str, ConfigValue] = {}
        for c in configs:
            for k, v in c.items():
                if isinstance(v, ConfigValue):
                    if k in out:
                        if out[k].priority < v.priority:
                            continue
                        # TODO log debug overwrite
                    out[k] = v
                else:
                    for c in configs:
                        c.setdefault(k, {})
                    configs_lower = [c[k] for c in configs]
                    out[k] = cls.merge_configs(*configs_lower)  # type:ignore

        return out

    def trait_values_from_func_signature(
        self, func: Callable, trait_select: dict | None = None, **kwargs
    ) -> dict:
        """Return trait values that appear in a function signature.

        Only consider the function arguments that can supplied as a keyword
        argument, and whose name is that of a configurable trait.
        Unbound arguments (ie ``**kwargs``) are ignored.

        Parameters
        ----------
        func:
            The callable to guess parameters from.
            Parameters are retrieved using :func:`inspect.signature()`.
            From its documentation: Accepts a wide range of callables: from
            plain functions and classes to :func:`functools.partial()` objects.
        trait_select:
            Passed to :meth:`trait_names`. Restrict to traits validating those
            conditions. Default is ``dict(config=True)``.
        kwargs:
            Passed to :func:`inspect.signature()`.

        Returns
        -------
        params:
            A mapping of parameters names to their values.
            Can be passed directly to ``func``.
        """
        sig = signature(func, **kwargs)
        params = {}

        if trait_select is None:
            trait_select = dict(config=True)
        trait_names = self.trait_names(**trait_select)

        for name, p in sig.parameters.items():
            if p.kind in [Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY]:
                print(name)
                if name in trait_names:
                    params[name] = getattr(self, name)

        return params
