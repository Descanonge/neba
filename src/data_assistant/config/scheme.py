"""Scheme: nested equivalent of Configurable.

Defines a :class:`Scheme` class meant to be used in place of
:class:`traitlets.config.Configurable` that make possible deeply nested configurations.
"""

from __future__ import annotations

import logging
import typing as t
from collections import abc
from inspect import Parameter, signature
from textwrap import dedent

from traitlets import Bool, Enum, Instance, TraitType
from traitlets.config import Configurable

from .loader import ConfigValue
from .util import (
    ConfigError,
    UnknownConfigKeyError,
    add_spacer,
    get_trait_typehint,
    indent,
    stringify,
    underline,
    wrap_text,
)

log = logging.getLogger(__name__)


def subscheme(scheme: type[Scheme]) -> Instance:
    """Transform a subscheme into a proper trait.

    To make the specification easier, an attribute of type :class:`Scheme` will
    automatically be transformed into a proper :class:`Instance` trait using this
    function. It can be used "manually" as well, this will most notably help static
    type checkers understand what is happening.

    So when specifying a subscheme the two lines below are equivalent:

        subgroup = MySubgroupScheme
        subgroup = subscheme(MySubgroupScheme)

    """
    return Instance(scheme, args=(), kw={}).tag(subscheme=True)


class Scheme(Configurable):
    """Object holding configurable values.

    This class inherits from :class:`traitlets.config.Configurable` and so can hold
    configurable attributes as :class:`traits<traitlets.TraitType>`, but also expands to
    allow nested configuration. Other Scheme classes can be set as attribute
    in order to specify parameters in deeper nested levels.

    The main features of this class are:

    * all traits are automatically tagged as configurable (``.tag(config=True)``),
      unless already tagged.
    * Any class attribute that is a subclass of Scheme will be registered as a nested
      *subscheme* and replaced by a :class:`traitlets.Instance` trait, tagged as a
      "subscheme" in its metadata.
    * Shortcuts to nested subschemes can be defined in the :attr:`aliases` attribute.
      This allows to specify shorter keys (in command line or config files).

    The API expand to recursively retrieve all traits (or their values) from this
    scheme and its subschemes. It defines help emitting functions, suitable for
    command line help message. It also enables having unique keys that point to a
    specific trait in the configuration tree (see :meth:`class_resolve_key`).
    """

    _subschemes: dict[str, type[Scheme]]
    """Mapping of nested Scheme classes."""

    _attr_completion_only_traits = Bool(
        False, help="Only keep configurable traits in attribute completion."
    )

    aliases: dict[str, str] = {}
    """Mapping of aliases/shortcuts.

    The shortcut name maps to the subscheme it points to, for example:

        {"short": "some.deeply.nested.subscheme"}

    will allow to specify parameters in two equivalent ways:

        some.deeply.nested.subscheme.my_parameter = 2
        short.my_parameter = 2
    """

    def __init_subclass__(cls, /, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._setup_scheme()

    @classmethod
    def _setup_scheme(cls) -> None:
        """Set up the class after definition.

        This hook is run in :meth:`__init_subclass__`, after any subclass of
        :class:`Scheme` is defined.

        By default, deals with the objective of Scheme: tagging all traits as
        configurable, and setting up attributes that are subclasses of Scheme
        as :class:`~traitlets.Instance` traits, and registering them as subschemes.

        This method can be modified by subclasses in need of specific behavior. Do not
        forget to call the ``super()`` version, and if traits are added/modified it
        might be necessary to call :meth:`traitlets.traitlets.HasTraits.setup_class`
        (``cls.setup_class(cls.__dict__)``).
        """
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
            if isinstance(v, Instance):
                # if v.klass is str, transform to corresponding type
                v._resolve_classes()
                assert isinstance(v.klass, type)  # maybe into a try/except block?
                if issubclass(v.klass, Scheme):
                    cls._subschemes[k] = v.klass
                    v.tag(subscheme=True, config=False)

        cls.setup_class(classdict)  # type: ignore

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.postinit()

    def postinit(self):
        """Run any instructions after instanciation.

        This allows to set/modify traits depending on other traits values.
        """
        pass

    def __str__(self) -> str:
        return self.__class__.__name__

    def __repr__(self) -> str:
        lines = [f"{self.__class__.__name__}:"]
        for key, trait in self.traits(config=True).items():
            if key in self._subschemes:
                continue
            trait_cls = trait.__class__.__name__
            value = trait.get(self)
            default = trait.default()
            lines.append(f"  -{key}: {value} [{trait_cls}, default: {default}]")

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

    def __dir__(self):
        if not self._attr_completion_only_traits:
            return super().__dir__()
        configurables = set(self.trait_names(config=True))
        subschemes = set(self._subschemes.keys())
        return configurables | subschemes

    @classmethod
    def _subschemes_recursive(cls) -> abc.Iterator[type[Scheme]]:
        """Iterate recursively over all subschemes."""
        for subscheme in cls._subschemes.values():
            yield from subscheme._subschemes_recursive()
        yield cls

    @classmethod
    def class_traits_recursive(cls) -> dict:
        """Return nested/recursive dict of all traits."""
        config: dict[t.Any, t.Any] = dict()
        config.update(cls.class_own_traits(config=True))
        for name, subscheme in cls._subschemes.items():
            config[name] = subscheme.class_traits_recursive()
        return config

    # Lifted from traitlets.config.application.Application
    @classmethod
    def _classes_inc_parents(
        cls, classes: abc.Sequence[type[Scheme]] | None = None
    ) -> abc.Generator[type[Configurable], None, None]:
        """Iterate through configurable classes, including configurable parents.

        Children should always be after parents, and each class should only be
        yielded once.

        Parameters
        ----------
        classes
            The list of classes to start from; if not set, uses all nested subschemes.
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

    def instanciate_subschemes(self, config: abc.Mapping):
        """Recursively instanciate subschemes.

        Parameters
        ----------
        config
            Nested configuration mapping attribute names to
        """
        for name, subscheme in self._subschemes.items():
            subconf = config.get(name, {})
            # discard further nested subschemes, only keep this level traits.
            kwargs = {
                t: subconf[t]
                for t in subscheme.class_trait_names(subscheme=None)
                if t in subconf
            }
            # Transform from ConfigValue to a value
            for key, val in kwargs.items():
                if isinstance(val, ConfigValue):
                    kwargs[key] = val.get_value()

            # set trait to a new instance
            self.set_trait(name, subscheme(parent=self, **kwargs))
            # recursive on this new instance
            getattr(self, name).instanciate_subschemes(subconf)

    def remap(
        self,
        func: abc.Callable[[Configurable, dict, str, TraitType, list[str]], None]
        | None,
        flatten: bool = False,
        **metadata,
    ) -> dict[str, t.Any]:
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
            for name, trait in scheme.traits(**metadata, subscheme=None).items():
                fullpath = path + [name]
                key = ".".join(fullpath) if flatten else name
                outsec[key] = trait
                if func is not None:
                    func(scheme, outsec, key, trait, fullpath)

            for name in scheme._subschemes:
                if flatten:
                    sub_outsec = outsec
                else:
                    outsec[name] = {}
                    sub_outsec = outsec[name]

                recurse(getattr(scheme, name), sub_outsec, path + [name])

        output: dict[str, t.Any] = dict()
        recurse(self, output, [])
        return output

    def traits_recursive(self, flatten: bool = False, **metadata) -> dict[str, t.Any]:
        """Return nested dictionnary of traits."""
        return self.remap(func=None, flatten=flatten, **metadata)

    def defaults_recursive(
        self, config=True, flatten: bool = False, **metadata
    ) -> dict[str, t.Any]:
        """Return nested dictionnary of default traits values."""

        def f(configurable, output, key, trait, path):
            output[key] = trait.default()

        output = self.remap(f, config=config, flatten=flatten, **metadata)
        return output

    def values_recursive(
        self, config=True, flatten: bool = False, **metadata
    ) -> dict[str, t.Any]:
        """Return nested dictionnary of traits values."""

        def f(configurable, output, key, trait, path):
            output[key] = trait.get(configurable)

        output = self.remap(f, config=config, flatten=flatten, **metadata)
        return output

    def values(self, select: list[str] | None = None) -> dict[str, t.Any]:
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
        """Resolve a key.

        This method is meant to be used pre-instanciation. Otherwise look to
        :meth:`resolve_key`.

        Parameters
        ----------
        key
            Dot separated (or a list of) attribute names that point to a trait in the
            configuration tree, starting from this Scheme.
            It might contain aliases/shortcuts.

        Returns
        -------
        fullkey
            Dot separated attribute names that *unambiguously* and *uniquely* point to a
            trait in the config tree, starting from this Scheme, ending with the trait
            name.
        subscheme
            The :class:`Scheme` *class* that contains the trait.
        trait
            The :class:`trait<traitlets.TraitType>` object corresponding to the key.
        """
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
                raise UnknownConfigKeyError(
                    f"Scheme '{'.'.join(fullkey)}' ({subscheme.__class__.__name__}) "
                    f"has no subscheme or alias '{subkey}'."
                )

        if not hasattr(subscheme, lastname):
            raise UnknownConfigKeyError(
                f"Scheme '{'.'.join(fullkey)}' ({subscheme.__class__.__name__}) "
                f"has no trait '{lastname}'."
            )
        trait = getattr(subscheme, lastname)

        return ".".join(fullkey + [lastname]), subscheme, trait

    def resolve_key(self, key: str | list[str]) -> tuple[str, Scheme, TraitType | None]:
        """Resolve a key.

        Parameters
        ----------
        key
            Dot separated (or a list of) attribute names that point to a trait in the
            configuration tree, starting from this Scheme.
            It might contain aliases/shortcuts.

        Returns
        -------
        fullkey
            Dot separated attribute names that *unambiguously* and *uniquely* point to a
            trait in the config tree, starting from this Scheme, ending with the trait
            name.
        subscheme
            The :class:`Scheme` *instance* that contains the trait.
        trait
            The :class:`trait<traitlets.TraitType>` object corresponding to the key.
        """
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
                raise UnknownConfigKeyError(
                    f"Scheme '{'.'.join(fullkey)}' ({subscheme.__class__.__name__}) "
                    f"has no subscheme or alias '{subkey}'."
                )

        if lastname not in subscheme.trait_names():
            raise UnknownConfigKeyError(
                f"Scheme '{'.'.join(fullkey)}' ({subscheme.__class__.__name__}) "
                f"has no trait '{lastname}'."
            )
        trait = subscheme.traits()[lastname]

        return ".".join(fullkey + [lastname]), subscheme, trait

    @classmethod
    def resolve_class_key(cls, key: str | list[str]) -> list[str]:
        """Resolve a "class key".

        Meaning a trait value specified as ``SchemeClassName.trait_name = ...``.
        Because *unlike in "native" traitlets* a Scheme can be used multiple times in
        the configuration tree (and still have instances with different configuration
        values), this method finds all occurences of the specified class and for each
        return the full key pointing to the trait.

        Parameters
        ----------
        key
            The key pointing to a trait either as a string like above, or a list
            resulting from ``key.split(".")``.

        Returns
        -------
        keys
            A list of dot separated attribute names that *unambiguously* and *uniquely*
            point to a trait in the config tree, starting from this Scheme, ending with
            the trait name.
        """
        if isinstance(key, str):
            key = key.split(".")
        if len(key) > 2:
            raise ConfigError(
                f"A parameter --Class.trait cannot be nested ({'.'.join(key)})."
            )

        clsname, traitname = key

        # Recurse throughout configuration tree to find matching classes
        def recurse(scheme: type[Scheme], fullpath: list[str]) -> abc.Iterator[str]:
            for name, subscheme in scheme._subschemes.items():
                newpath = fullpath + [name]
                if subscheme.__name__ == clsname:
                    yield ".".join(newpath + [traitname])
                yield from recurse(subscheme, newpath)

        return list(recurse(cls, []))

    @classmethod
    def merge_configs(
        cls,
        *configs: abc.Mapping[str, ConfigValue],
    ) -> dict[str, ConfigValue]:
        """Merge multiple flat configuration mappings.

        The configurations should have been resolved with :meth:`resolve_config`. If
        there is a conflict between values, configurations specified *later* in the
        argument list will take priority (ie last one wins). The value from the
        precedent config is replaced if the :attr:`value's
        priority<.config.loader.ConfigValue.priority>` is equal or higher.
        """
        out: dict[str, ConfigValue] = {}
        for c in configs:
            for k, v in c.items():
                if k in out:
                    if v.priority < out[k].priority:
                        continue
                    log.debug(
                        "Parameter '%s' with value '%s' (from %s) has been overwritten "
                        "by value '%s' (from %s).",
                        k,
                        str(out[k].value),
                        out[k].origin,
                        str(v.value),
                        v.origin,
                    )
                out[k] = v

        return out

    def help(self) -> None:
        """Print description of this scheme and its traits."""
        print("\n".join(self.emit_help()))

    def emit_help(self, fullpath: list[str] | None = None) -> list[str]:
        """Return help for this scheme, and its subschemes recursively.

        Contains the name of this scheme, its description if it has one, eventual
        aliases/shortcuts, help on each trait, and same thing recursively on subschemes.

        Format the help so that it can be used as help for specifying values from the
        command line.
        """
        if fullpath is None:
            fullpath = []

        title = self.__class__.__name__
        if fullpath:  # we are not at root
            title = f"{'.'.join(fullpath)} ({title})"
        lines = [title]
        underline(lines)

        description = self.emit_description()
        if description:
            lines += description
            lines.append("")

        # aliases
        if self.aliases:
            add_spacer(lines)
            lines.append("Aliases:")
            underline(lines)
            for short, long in self.aliases.items():
                lines.append(f"{short}: {long}")

        for name, trait in sorted(self.traits(config=True).items()):
            lines += indent(
                self.emit_trait_help(fullpath + [name], trait), initial_indent=False
            )

        for name in sorted(self._subschemes):
            add_spacer(lines)
            lines += getattr(self, name).emit_help(fullpath + [name])

        return lines

    def emit_description(self) -> list[str]:
        """Return lines of description of this scheme.

        Take the scheme docstring if defined, and format it nicely (wraps it, remove
        trailing whitespace, etc.). Return a list of lines.
        """
        doc = self.__doc__
        if not doc:
            return []

        # Remove leading and trailing whitespace
        doc = doc.strip()
        lines = doc.splitlines()
        if len(lines) > 1:
            # dedent, ignoring first line that has no indent in docstrigs
            trimmed = dedent("\n".join(lines[1:]))
            # put it back together
            lines = lines[:1] + trimmed.splitlines()

        return lines

    def emit_trait_help(self, fullpath: list[str], trait: TraitType) -> list[str]:
        """Return lines of help for a trait of this scheme.

        Format the help so that it can be used as help for specifying values from the
        command line.
        """
        lines: list[str] = []

        name = fullpath[-1]
        value = stringify(trait.default(), rst=False)
        typehint = get_trait_typehint(trait, mode="minimal")
        fullkey = ".".join(fullpath)
        lines += [f"{name} ({typehint})", f"--{fullkey} = {value}"]

        if isinstance(trait, Enum):
            lines.append("Accepted values: " + repr(trait.values))

        if trait.help:
            lines += wrap_text(trait.help)

        return lines

    def trait_values_from_func_signature(
        self, func: abc.Callable, trait_select: abc.Mapping | None = None, **kwargs
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
