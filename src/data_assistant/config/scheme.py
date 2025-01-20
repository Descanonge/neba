"""Scheme: nested equivalent of Configurable.

Defines a :class:`Scheme` class meant to be used in place of
:class:`traitlets.config.Configurable` that make possible deeply nested configurations.
"""

from __future__ import annotations

import itertools
import logging
import typing as t
from collections import abc
from inspect import Parameter, signature
from textwrap import dedent

from traitlets import Bool, Enum, Instance, Sentinel, TraitType, Undefined
from traitlets.config import Configurable

from .loaders import ConfigValue
from .util import (
    ConfigError,
    UnknownConfigKeyError,
    add_spacer,
    get_trait_typehint,
    indent,
    nest_dict,
    stringify,
    underline,
    wrap_text,
)

log = logging.getLogger(__name__)


S = t.TypeVar("S", bound="Scheme")


def subscheme(scheme: type[S]) -> Instance[S]:
    """Transform a subscheme into a proper trait.

    To make the specification easier, an attribute of type :class:`Scheme` will
    automatically be transformed into a proper :class:`Instance` trait using this
    function. It can be used "manually" as well, this will most notably help static
    type checkers understand what is happening.

    So when specifying a subscheme the two lines below are equivalent::

        subgroup = MySubgroupScheme
        subgroup = subscheme(MySubgroupScheme)

    """
    return Instance(scheme, args=(), kw={}).tag(subscheme=True, config=False)


def _name_to_classdef(name: str) -> str:
    return f"_{name}SchemeDef"


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
    * Any nested class definition (subclass of Scheme) will also be considered as a
      subscheme whose name is that of the class. The class definition will be kept under
      another attribute name (``_{subscheme}SchemeDef``).
    * Shortcuts to nested subschemes can be defined in the :attr:`aliases` attribute.
      This allows to specify shorter keys (in command line or config files).

    The API expand to recursively retrieve all traits (or their values) from this
    scheme and its subschemes. It defines help emitting functions, suitable for
    command line help message. It also enables having unique keys that point to a
    specific trait in the configuration tree (see :meth:`resolve_key`).
    """

    _subschemes: dict[str, type[Scheme]] = {}
    """Mapping of nested Scheme classes."""

    _attr_completion_only_traits = Bool(
        False, help="Only keep configurable traits in attribute completion."
    )

    _dynamic_subschemes = True
    """Allow dynamic definition of subschemes.

    Any attribute that is a Scheme will be converted to a trait instance and added to
    the subschemes. Class definitions will be modified appropriately.
    """

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

        to_add: dict[str, type[Scheme]] = {}

        for k, v in classdict.items():
            # tag traits as configurable
            if isinstance(v, TraitType):
                if v.metadata.get("config", True):
                    v.tag(config=True)

            if not cls._dynamic_subschemes:
                continue

            # Add Scheme definitions
            if isinstance(v, type) and issubclass(v, Scheme) and k == v.__name__:
                to_add[k.rstrip("_")] = v

        for k, v in to_add.items():
            # change location of class definition
            new_name = _name_to_classdef(k)
            v.__name__ = new_name
            v.__qualname__ = f"{cls.__qualname__}.{new_name}"
            setattr(cls, new_name, v)

            # And add a subscheme
            setattr(cls, k, subscheme(v))

        # add ancestors subschemes
        for base in cls.__bases__:
            if issubclass(base, Scheme):
                cls._subschemes |= base._subschemes

        # register new subschemes
        for k, v in classdict.items():
            if isinstance(v, Instance):
                # if v.klass is str, transform to corresponding type
                v._resolve_classes()
                assert isinstance(v.klass, type)  # maybe into a try/except block?
                if issubclass(v.klass, Scheme):
                    cls._subschemes[k] = v.klass
                    v.tag(subscheme=True, config=False)

        cls.setup_class(classdict)  # type: ignore

        # Check aliases
        for short, alias in cls.aliases.items():
            subscheme_cls = cls
            for key in alias.split("."):
                try:
                    subscheme_cls = subscheme_cls._subschemes[key]
                except KeyError as err:
                    raise KeyError(
                        f"Alias '{short}:{alias}' in {cls.__name__} malformed."
                    ) from err

    # TODO Support nested config dictionary, or dot-separated kwargs
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
        return "\n".join(self._get_lines())

    def _get_lines(self, header: str = "") -> list[str]:
        line = "\u2574"
        branch = "\u251c" + line
        elbow = "\u2514" + line
        branch_subscheme = "\u251d" + "\u2501" * len(line) + "\u2511"
        elbow_subscheme = "\u2515" + "\u2501" * len(line) + "\u2511"
        pipe = "\u2502" + " " * len(line)
        blank = " " * len(pipe)

        lines = [self.__class__.__name__]
        traits = self.traits(config=True, subscheme=None)
        for i, (key, trait) in enumerate(traits.items()):
            symb = branch
            if i == len(traits) - 1 and not self._subschemes:
                symb = elbow

            trait_cls = get_trait_typehint(trait, mode="minimal")
            value = trait.get(self)
            default = trait.default()

            to_add = []
            if value != default:
                to_add += [f"default: {default}"]
            if isinstance(trait, Enum) and trait.values is not None:
                to_add += [str(trait.values)]

            trait_str = f"{trait_cls}"
            if to_add:
                trait_str += f"[{', '.join(to_add)}]"
            trait_str = f"({trait_str})"

            lines.append(f"{header}{symb}{key}: {value}  {trait_str}")

        for i, name in enumerate(self._subschemes):
            lines.append(header + pipe)
            is_last = i == len(self._subschemes) - 1

            subscheme: Scheme = getattr(self, name)
            sublines = subscheme._get_lines(header + (blank if is_last else pipe))

            symb = elbow_subscheme if is_last else branch_subscheme
            sublines[0] = f"{header}{symb}{name}:"
            lines += sublines

        return lines

    def __dir__(self):
        if not self._attr_completion_only_traits:
            return super().__dir__()
        configurables = set(self.trait_names(config=True))
        subschemes = set(self._subschemes.keys())
        return configurables | subschemes

    # - Mapping methods

    def keys(
        self, subschemes: bool = False, recursive: bool = True, aliases: bool = False
    ) -> list[str]:
        """Return iterable of keys leading to subschemes and traits.

        Parameters
        ----------
        subschemes
            If True (default is False), keys can lead to subschemes instances.
        recursive
            If True (default), return keys for parameters from all subschemes.
        aliases
            If True (default is False), include aliases.
        """
        return list(
            self._keys(subschemes=subschemes, recursive=recursive, aliases=aliases)
        )

    def _keys(
        self, subschemes: bool = False, recursive: bool = True, aliases: bool = False
    ) -> abc.Generator[str]:
        trait_names = self.trait_names(subscheme=None, config=True)
        yield from filter(lambda s: not s.startswith("_"), trait_names)

        subs: list[abc.Iterable] = [self._subschemes]
        if aliases:
            subs.append(self.aliases.keys())

        for name in itertools.chain(*subs):
            subscheme = self[name]
            if subschemes:
                yield name
            if recursive:
                sub_traits = subscheme.keys(subschemes=subschemes, aliases=aliases)
                yield from (f"{name}.{s}" for s in sub_traits)

    def values(
        self, subschemes: bool = False, recursive: bool = True, aliases: bool = False
    ) -> list[t.Any]:
        """List of subschemes instances and trait values.

        In the same order as :meth:`keys`.

        Parameters
        ----------
        subschemes
            If True (default is False), values include subschemes instances.
        recursive
            If True (default), return all subschemes.
        aliases
            If True (default is False), include aliases.
        """
        keys = self.keys(subschemes=subschemes, recursive=recursive, aliases=aliases)
        return [self[key] for key in keys]

    def items(
        self, subschemes: bool = False, recursive: bool = True, aliases: bool = False
    ) -> list[tuple[str, t.Any]]:
        """Return mapping of keys to values.

        Keys can lead to subschemes instances or trait values.

        Parameters
        ----------
        subschemes
            If True (default is False), keys can map to subschemes instances.
        recursive
            If True (default), return parameters from all subschemes. Otherwise limit to
            only this scheme.
        aliases
            If True (default is False), include aliases.
        """
        keys = self.keys(subschemes=subschemes, recursive=recursive, aliases=aliases)
        return [(key, self[key]) for key in keys]

    def get(self, key: str, default: t.Any | None = None) -> t.Any:
        """Obtain value at `key`."""
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: str) -> t.Any:
        """Obtain value it `key`."""
        fullpath = key.split(".")
        subscheme = self
        for i, name in enumerate(fullpath):
            if name in subscheme._subschemes:
                subscheme = getattr(subscheme, name)
                continue
            elif name in subscheme.aliases:
                subscheme = subscheme[subscheme.aliases[name]]
                continue
            if i == len(fullpath) - 1 and name in subscheme.trait_names(config=True):
                return getattr(subscheme, name)
                continue
            raise KeyError(
                f"Could not resolve key {key} "
                f"('{name}' not in {subscheme.__class__.__name__})"
            )

        return subscheme

    def __contains__(self, key: str) -> bool:
        """Return if key leads to an existing subscheme or trait."""
        return key in self.keys(subschemes=True, aliases=True)

    def __iter__(self) -> abc.Iterable[str]:
        """Iterate over possible keys.

        Simply iter :meth:`keys`.
        """
        return iter(self.keys())

    def __len__(self) -> int:
        """Return number of valid keys."""
        return len(list(self.keys()))

    def __eq__(self, other: t.Any) -> bool:
        """Check equality with other scheme.

        If *other* is not a Scheme, will return False. Both scheme must have the same
        keys and same values.
        """
        if not isinstance(other, type(self)):
            return False
        # Check that we have the same keys
        if set(self.keys()) != set(other.keys()):
            return False
        return dict(self) == dict(other)

    def __ne__(self, other: t.Any) -> bool:
        return not self == other

    # - end of Mapping methods
    # - Mutable Mapping methods

    def __setitem__(self, key: str, value: t.Any):
        """Set a trait to a value.

        Parameters
        ----------
        key
            Path to leading to a trait.
        """
        *prefix, trait_name = key.split(".")
        if len(prefix) == 0:
            subscheme = self
        else:
            subscheme = self[".".join(prefix)]

        if trait_name not in subscheme.trait_names():
            clsname = subscheme.__class__.__name__
            raise KeyError(f"No trait '{trait_name}' in scheme {clsname}.")

        setattr(subscheme, trait_name, value)

    def setdefault(
        self,
        key: str,
        default: TraitType | None = None,
        value: t.Any | Sentinel = Undefined,
    ) -> t.Any:
        """Set a trait to a value if it exists.

        If the trait exists, return its value. Otherwise, the *default* argument must be
        provide a trait instance to add it to the scheme, it is set to *value* if it is
        provided as well.

        Parameters
        ----------
        key
            Path to leading to a trait.
        default
            Trait instance to add.
        value
            Value to set the new trait to if *key* does not lead to an existing trait.
            Can be left undefined if the trait has a default value.
        """
        if key in self:
            return self[key]
        if default is None:
            raise TypeError(
                f"Key '{key}' does not exist. A trait argument must be "
                " supplied to be added to the scheme."
            )
        self.add_trait(key, default)
        if value is not Undefined:
            self[key] = value

        return self[key]

    def pop(self, key: str, other: t.Any | None = None) -> t.Any:
        """Schemes do not support the *pop* operation.

        A trait cannot be deleted.
        """
        raise TypeError("Schemes do not support 'pop'. A trait cannot be deleted")

    def popitem(self) -> tuple[str, t.Any]:
        """Schemes do not support the *popitem* operation.

        A trait cannot be deleted.
        """
        raise TypeError("Schemes do not support 'popitem'. A trait cannot be deleted")

    def clear(self) -> None:
        """Schemes do not support the *clear* operation.

        A trait cannot be deleted. You may use :meth:`reset` to reset all traits to
        their default value.
        """
        raise TypeError(
            "Schemes do not support 'clear'. A trait cannot be deleted. "
            "You may use 'reset' to reset all traits to their default value."
        )

    def reset(self) -> None:
        """Reset all traits to their default value."""

        def func(scheme: Configurable, traits, key: str, trait: TraitType, path):
            setattr(scheme, key, trait.default())

        self.remap(func, config=True)

    def update(
        self,
        other: Scheme | abc.Mapping[str, t.Any] | None = None,
        allow_new: bool = False,
        raise_on_miss: bool = False,
        **kwargs,
    ):
        """Update values of this Scheme traits.

        Some trait that do not exist in this instance, but are specified can be added.
        Currently whole subschemes cannot be added.

        Parameters
        ----------
        other
            Other Scheme to take traits values from (recursively). It can also be a
            flat mapping of full path keys (``"some.path.to.trait"``) to values or
            trait instances, which default value will be used.
        allow_new
            If True, allow creating new traits for this Scheme. A new trait must can be
            a trait in `other` if it is a Scheme; in a mapping it must be a trait
            instance which default value will be used. Default is False.
        raise_on_miss
            If True, raise an exception if a trait in `other` is placed on a path that
            does not lead to an existing subscheme or trait. Default is False.
        kwargs
            Same as `other`.
        """
        input_scheme = False
        values: dict[str, t.Any]
        if other is None:
            values = {}
        elif isinstance(other, Scheme):
            values = dict(other)
            input_scheme = True
        else:
            values = dict(other)
        values |= kwargs

        for key, value in values.items():
            if key not in self:
                if raise_on_miss:
                    raise KeyError(f"Trait '{key}' does not exist in {self}")
                if not allow_new:
                    raise RuntimeError(f"Trait creation was not authorized ({key})")

                if isinstance(value, TraitType):
                    newtrait = value
                elif input_scheme:
                    newtrait = other.traits_recursive(flatten=True)[key]  # type: ignore[union-attr]
                else:
                    raise TypeError(
                        "A new trait must be specified as a TraitType or from a Scheme "
                        f"({key}: {type(value)})"
                    )

                self.add_trait(key, newtrait)

            # trait exists or has been added
            if isinstance(value, TraitType):
                value = value.default

            self[key] = value

    # - end of Mutable Mapping methods

    def add_trait(self, key: str, trait: TraitType, allow_recursive: bool = True):
        """Add a trait to this scheme or one of its subscheme.

        The trait name cannot be already in use.

        Parameters
        ----------
        key
            Path of dot separated attribute names leading to the trait to add. It can
            also only be a trait name to add to *this* scheme.
        trait
            Trait instance to add.
        allow_recursive
            If True (default), subschemes specified in *key* that are not contained in
            this scheme will be added automatically. Otherwise, this will raise on
            unknown subschemes in *key*.
        """
        *prefix, trait_name = key.split(".")

        scheme = self
        for name in prefix:
            if name in scheme._subschemes:
                pass
            # subscheme does not exist
            elif allow_recursive:
                scheme.add_traits(**{name: subscheme(Scheme)})
                scheme._subschemes[name] = Scheme
            else:
                raise KeyError(
                    f"There is no scheme '{name}', and creating subschemes "
                    f"to add trait '{key}' was not allowed."
                )

            # scheme exists or has been added
            scheme = getattr(scheme, name)

        if trait_name in scheme.trait_names():
            raise KeyError(f"Trait '{key}' already exists.")

        scheme.add_traits(**{trait_name: trait})

    def as_dict(
        self, recursive: bool = True, aliases: bool = False, flatten: bool = True
    ) -> dict[str, t.Any]:
        """Return traits as a dictionary.

        Parameters
        ----------
        recursive
            If True (default), return parameters from all subschemes. Otherwise limit to
            only this scheme.
        aliases
            If True (default is False), include aliases.
        flatten
            If True (default), return a flat dictionnary with dot-separated keys.
            Otherwise return a nested dictionnary.
        """
        output = dict(
            self.items(subschemes=False, recursive=recursive, aliases=aliases)
        )
        if not flatten:
            output = nest_dict(output)
        return output

    def select(self, *keys: str, flatten: bool = False) -> dict[str, t.Any]:
        """Select parameters from this schemes or its subschemes.

        Parameters
        ----------
        keys
            Keys leading to parameters. To select parameters from subschemes, use
            dot-separated syntax like ``"some.nested.parameter"``.
        flatten
            If True (default), return a flat dictionnary with dot-separated keys.
            Otherwise return a nested dictionnary.
        """
        output = {k: self[k] for k in keys}
        if not flatten:
            output = nest_dict(output)
        return output

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
        cls, classes: abc.Iterable[type[Scheme]] | None = None
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
            classes = cls._subschemes_recursive()

        seen = set()
        for c in classes:
            # We want to sort parents before children, so we reverse the MRO
            for parent in reversed(c.mro()):
                if issubclass(parent, Configurable) and (parent not in seen):
                    seen.add(parent)
                    yield parent

    @classmethod
    def instanciate_recursively(cls, config: abc.Mapping, **kwargs) -> t.Self:
        """Instanciate this class and its subschemes with values from config.

        Parameters
        ----------
        config
            Nested configuration mapping attribute names of traits to values (or
            ConfigValue) nest on subschemes.
        kwargs
            Passed to `__init__`. Used for passing *parent* keyword.
        """
        my_conf = cls.get_subconfig(config, subscheme=None)
        me = cls(**my_conf, **kwargs)

        # Instanciate and set subschemes
        for name, subcls in me._subschemes.items():
            subconf = config.get(name, {})
            sub_instance = subcls.instanciate_recursively(subconf, parent=me)
            me.set_trait(name, sub_instance)
        return me

    @classmethod
    def get_subconfig(cls, config: abc.Mapping, **select) -> dict:
        """Return only the parameters corresponding to traits of `obj`.

        Parameters
        ----------
        config
            Nested mapping from trait names to values or ConfigValue. If a ConfigValue, it
            it converted to a plain value with :meth:`.ConfigValue.get_value`.
        select
            Is used to further constrain the traits to keep.
        """
        out = {
            name: config[name]
            for name in cls.class_trait_names(**select)
            if name in config
        }
        for k, v in out.items():
            if isinstance(v, ConfigValue):
                out[k] = v.get_value()
        return out

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
        flatten:
            If True, return a flat dictionary (not nested) with each key being the full
            path of subscheme leading to a trait, separated by dots (ie
            ``"some.path.to.trait"``). Default is False.
        metadata:
            Select only some traits which metadata satistify this argument.
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
        """Return nested dictionnary of traits values.

        .. important:: For users

            Consider using :meth:`as_dict` instead. The result is
            the same (save for ordering of keys). Its code is simpler,
            better tested. Use this method if you need to select
            traits using their metadata.
        """

        def f(configurable, output, key, trait, path):
            output[key] = trait.get(configurable)

        output = self.remap(f, config=config, flatten=flatten, **metadata)
        return output

    @classmethod
    def resolve_key(cls, key: str | list[str]) -> tuple[str, type[Scheme], TraitType]:
        """Resolve a key.

        This method is meant to be used pre-instanciation.

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

        *prefix, trait_name = key
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
                    f"Scheme '{'.'.join(fullkey)}' ({_subscheme_clsname(subscheme)}) "
                    f"has no subscheme or alias '{subkey}'."
                )

        if not hasattr(subscheme, trait_name):
            raise UnknownConfigKeyError(
                f"Scheme '{'.'.join(fullkey)}' ({_subscheme_clsname(subscheme)}) "
                f"has no trait '{trait_name}'."
            )
        trait = getattr(subscheme, trait_name)

        return ".".join(fullkey + [trait_name]), subscheme, trait

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

        clsname, trait_name = key

        # Recurse throughout configuration tree to find matching classes
        def recurse(scheme: type[Scheme], fullpath: list[str]) -> abc.Iterator[str]:
            if scheme.__name__ == clsname:
                yield ".".join(fullpath + [trait_name])
            for name, subscheme in scheme._subschemes.items():
                newpath = fullpath + [name]
                yield from recurse(subscheme, newpath)

        return list(recurse(cls, []))

    @classmethod
    def merge_configs(
        cls,
        *configs: abc.Mapping[str, ConfigValue],
    ) -> dict[str, ConfigValue]:
        """Merge multiple flat configuration mappings.

        If there is a conflict between values, configurations specified *later* in the
        argument list will take priority (ie last one wins). The value from the
        precedent config is replaced if the :attr:`value's
        priority<.ConfigValue.priority>` is equal or higher.
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
        A trait without value (specified or default) will be ignored.
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
                if name in trait_names:
                    value = getattr(self, name)
                    if value is Undefined:
                        continue
                    params[name] = value

        return params


def _subscheme_clsname(scheme: type[Scheme] | Scheme, module: bool = True) -> str:
    if not isinstance(scheme, type):
        scheme = scheme.__class__

    mod = ""
    if module:
        try:
            mod = scheme.__module__
        except AttributeError:
            pass

    try:
        name = scheme.__qualname__
    except AttributeError:
        return str(scheme)

    return ".".join([mod, name])


abc.MutableMapping[str, t.Any].register(Scheme)
