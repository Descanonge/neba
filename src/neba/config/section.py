"""Section: nested equivalent of Configurable.

Defines a :class:`Section` class meant to be used in place of
:class:`traitlets.config.Configurable` that make possible deeply nested configurations.
"""

from __future__ import annotations

import logging
from collections.abc import (
    Callable,
    Generator,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
)
from inspect import Parameter, signature
from textwrap import dedent
from typing import Any, Generic, Literal, Self, TypeVar, overload

from traitlets import Enum, HasTraits, Sentinel, TraitType, Undefined

from neba.utils import did_you_mean, get_classname

from .docs import (
    add_spacer,
    get_trait_typehint,
    indent,
    stringify,
    underline,
    wrap_text,
)
from .loaders import ConfigValue
from .types import UnknownConfigKeyError

log = logging.getLogger(__name__)


S = TypeVar("S", bound="Section")

_line = "\u2574"
_branch = "\u251c" + _line
_elbow = "\u2514" + _line
_branch_subsection = "\u251d" + "\u2501" * len(_line) + "\u2511"
_elbow_subsection = "\u2515" + "\u2501" * len(_line) + "\u2511"
_pipe = "\u2502" + " " * len(_line)
_blank = " " * len(_pipe)


class Subsection(Generic[S]):
    """Descriptor for subsection.

    I do not use traitlets.Instance because it initializes eagerly, I would prefer to
    wait before initializing recursively all subsections.
    """

    klass: type[S]
    private_name: str

    def __init__(self, section: type[S]) -> None:
        self.klass = section

    def __set_name__(self, owner: type[S], name: str) -> None:
        self.private_name = "__" + name

    @overload
    def __get__(self, obj: None, owner: type[Any]) -> Self: ...

    @overload
    def __get__(self, obj: Section, owner: type[Any]) -> S: ...

    def __get__(self, obj: Section | None, owner: type[Any]) -> Self | S:
        if obj is None:
            return self
        if not hasattr(obj, self.private_name):
            raise AttributeError(
                f"Subsection {self.private_name} has not been initialized."
            )
        return getattr(obj, self.private_name)

    def __set__(self, obj: Section, value: S) -> None:
        setattr(obj, self.private_name, value)


class Section(HasTraits):
    """Object holding configurable values.

    This class inherits from :class:`traitlets.config.Configurable` and so can hold
    configurable attributes as :class:`traits<traitlets.TraitType>`, but also expands to
    allow nested configuration. Other Section classes can be set as attribute
    in order to specify parameters in deeper nested levels.

    The main features of this class are:

    * all traits are automatically tagged as configurable (``.tag(config=True)``),
      unless already tagged.
    * Any class attribute that is a subclass of Section will be registered as a nested
      *subsection* and replaced by a :class:`.Subsection` descriptor..
    * Any nested class definition (subclass of Section) will also be considered as a
      subsection whose name is that of the class. The class definition will be kept under
      another attribute name (``_{subsection}SectionDef``).
    * Shortcuts to nested subsections can be defined in the :attr:`aliases` attribute.
      This allows to specify shorter keys (in command line or config files).

    The API expand to recursively retrieve all traits (or their values) from this
    section and its subsections. It defines help emitting functions, suitable for
    command line help message. It also enables having unique keys that point to a
    specific trait in the configuration tree (see :meth:`resolve_key`).
    """

    _subsections: dict[str, Subsection] = {}
    """Mapping of subsections descriptors."""

    _attr_completion_only_traits: bool = False
    """Only keep configurable traits in attribute completion."""

    _dynamic_subsections = True
    """Allow dynamic definition of subsections.

    Any attribute that is a Section will be converted to a trait instance and added to
    the subsections. Class definitions will be modified appropriately.
    """

    aliases: dict[str, str] = {}
    """Mapping of aliases/shortcuts.

    The shortcut name maps to the subsection it points to, for example:

        {"short": "some.deeply.nested.subsection"}

    will allow to specify parameters in two equivalent ways:

        some.deeply.nested.subsection.my_parameter = 2
        short.my_parameter = 2
    """

    def __init_subclass__(cls, /, **kwargs: Any) -> None:
        """Call :meth:`_setup_section`."""
        super().__init_subclass__(**kwargs)
        cls._setup_section()

    @classmethod
    def _setup_section(cls) -> None:
        """Set up the class after definition.

        This hook is run in :meth:`__init_subclass__`, after any subclass of
        :class:`Section` is defined.

        This method can be modified by subclasses in need of specific behavior. Do not
        forget to call the ``super()`` version, and if traits are added/modified it
        might be necessary to call :meth:`traitlets.traitlets.HasTraits.setup_class`
        (``cls.setup_class(cls.__dict__)``).
        """
        cls._subsections = {}
        classdict = cls.__dict__
        to_add: dict[str, Any] = {}

        for k, v in classdict.items():
            # tag traits as configurable
            if isinstance(v, TraitType):
                if v.metadata.get("config", True):
                    v.tag(config=True)

            if (
                cls._dynamic_subsections
                and isinstance(v, type)
                and issubclass(v, Section)
                and v.__qualname__ == f"{cls.__qualname__}.{v.__name__}"
            ):
                # change location of class definition
                new_name = f"_{k}SectionDef"
                v.__name__ = new_name
                v.__qualname__ = f"{cls.__qualname__}.{new_name}"
                to_add[new_name] = v
                subsec = Subsection(v)
                subsec.__set_name__(cls, k)
                to_add[k] = subsec

        for k, v in to_add.items():
            setattr(cls, k, v)

        # register subsections
        for k, v in classdict.items():
            if isinstance(v, Subsection):
                cls._subsections[k] = v

        # add ancestors subsections
        for base in cls.__bases__:
            if issubclass(base, Section):
                cls._subsections |= base._subsections

        cls.setup_class(classdict)  # type: ignore

        # Check aliases
        for short, alias in cls.aliases.items():
            if "." in short:
                raise ValueError(f"Invalid alias '{short}': '.' is not allowed.")
            subsection_cls = cls
            for key in alias.split("."):
                try:
                    subsection_cls = subsection_cls._subsections[key].klass
                except KeyError as err:
                    raise KeyError(
                        f"Alias '{short}:{alias}' in {cls.__name__} malformed."
                    ) from err

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        init_subsections: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize section.

        Parameters
        ----------
        config
            Flat dictionary containing values for the traits of this section, and
            its subsections. If a value is missing, the trait default value is used.
        """
        self._parent: Section | None = None
        self._name: str = ""

        if config is None:
            config = {}

        config = dict(config)  # copy
        config |= kwargs

        with self.hold_trait_notifications():
            self._init_direct_traits(config)
        if init_subsections:
            self._init_subsections(config)

        if config:
            raise KeyError(
                f"Extra parameters for {self.__class__.__name__} {list(config.keys())}"
            )

        self.postinit()

    def _init_direct_traits(self, config: dict[str, Any]) -> None:
        for name in self.trait_names(config=True):
            if name in config:
                value = config.pop(name)
                if isinstance(value, ConfigValue):
                    value = value.get_value()
                setattr(self, name, value)

    def _init_subsections(self, config: dict[str, Any]) -> None:
        for name, subsection_cls in self.class_subsections().items():
            prefix = f"{name}."
            subconfig = {k: v for k, v in config.items() if k.startswith(prefix)}
            for k in subconfig:
                config.pop(k)
            subconfig = {k.removeprefix(prefix): v for k, v in subconfig.items()}
            subsection = subsection_cls(subconfig)
            subsection._parent = self
            subsection._name = name
            setattr(self, name, subsection)

    def postinit(self) -> None:
        """Run any instructions after instantiation.

        This allows to set/modify traits depending on other traits values.
        """
        pass

    def __str__(self) -> str:
        return self.__class__.__name__

    def __repr__(self) -> str:
        return "\n".join(self._get_lines())

    def _get_lines(self, header: str = "") -> list[str]:
        lines = [self.__class__.__name__]
        traits = self.traits(config=True)
        for i, (key, trait) in enumerate(traits.items()):
            is_last = i == len(traits) - 1 and not self._subsections
            lines.append(
                header + self._get_line_trait(key, trait, is_last, trait.get(self))
            )

        for i, name in enumerate(self._subsections):
            # not instianted
            if not hasattr(self, name):
                continue
            lines.append(header + _pipe)
            is_last = i == len(self._subsections) - 1

            subsection: Section = getattr(self, name)
            sublines = subsection._get_lines(header + (_blank if is_last else _pipe))

            symb = _elbow_subsection if is_last else _branch_subsection
            sublines[0] = f"{header}{symb}{name}:"
            lines += sublines

        return lines

    @classmethod
    def _get_line_trait(
        cls, key: str, trait: TraitType | None, elbow: bool, value: Any
    ) -> str:
        symb = _elbow if elbow else _branch
        if trait is None:
            return f"{symb}{key}: {value}"

        trait_cls = get_trait_typehint(trait, mode="minimal")
        default = trait.default()

        to_add = []
        if isinstance(trait, Enum) and trait.values is not None:
            to_add += [repr(v) for v in trait.values]
        if value != default:
            to_add += [f"default: {default}"]

        trait_str = f"{trait_cls}"
        if to_add:
            trait_str += f" [{', '.join(to_add)}]"
        trait_str = f"({trait_str})"

        return f"{symb}{key}: {value}  {trait_str}"

    def __dir__(self) -> Iterable[str]:
        if not self._attr_completion_only_traits:
            return super().__dir__()
        configurables = set(self.trait_names(config=True))
        subsections = set(self._subsections.keys())
        return configurables | subsections

    def __getattr__(self, name: str) -> Any:
        """Patch for "did you mean" feature."""
        clsname = type(self).__qualname__
        section_name = object.__getattribute__(self, "_name")
        msg = (
            f"Section '{section_name}' ({clsname})"
            if section_name
            else f"'{clsname}' object"
        )
        msg += f" has no attribute '{name}'"
        if (suggestion := did_you_mean(super().__dir__(), name)) is not None:
            msg += f" (did you mean '{suggestion}'?)"
        raise AttributeError(msg)

    def copy(self, **kwargs: Any) -> Self:
        """Return a copy."""
        config = self.as_dict()
        return self.__class__(config, **kwargs)

    # - Mapping methods

    def keys(
        self, subsections: bool = False, recursive: bool = True, aliases: bool = False
    ) -> list[str]:
        """Return list of keys leading to subsections and traits.

        Parameters
        ----------
        subsections
            If True (default is False), keys can lead to subsections instances.
        recursive
            If True (default), return keys for parameters from all subsections.
        aliases
            If True (default is False), include aliases.
        """
        return [
            name
            for name, _ in self._iter_traits(
                subsections=subsections,
                recursive=recursive,
                aliases=aliases,
                config=True,
            )
        ]

    def values(
        self, subsections: bool = False, recursive: bool = True, aliases: bool = False
    ) -> list[Any]:
        """List of subsections instances and trait values.

        In the same order as :meth:`keys`.

        Parameters
        ----------
        subsections
            If True (default is False), values include subsections instances.
        recursive
            If True (default), return all subsections.
        aliases
            If True (default is False), include aliases.
        """
        keys = self.keys(subsections=subsections, recursive=recursive, aliases=aliases)
        return [self[key] for key in keys]

    def items(
        self, subsections: bool = False, recursive: bool = True, aliases: bool = False
    ) -> list[tuple[str, Any]]:
        """Return mapping of keys to values.

        Keys can lead to subsections instances or trait values.

        Parameters
        ----------
        subsections
            If True (default is False), keys can map to subsections instances.
        recursive
            If True (default), return parameters from all subsections. Otherwise limit to
            only this section.
        aliases
            If True (default is False), include aliases.
        """
        keys = self.keys(subsections=subsections, recursive=recursive, aliases=aliases)
        return [(key, self[key]) for key in keys]

    def get(self, key: str, default: Any | None = None) -> Any:
        """Obtain value at `key`."""
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: str) -> Any:
        """Obtain value at `key`."""
        fullpath = key.split(".")
        subsection = self
        for i, name in enumerate(fullpath):
            if name in subsection._subsections:
                subsection = getattr(subsection, name)
                continue
            elif name in subsection.aliases:
                subsection = subsection[subsection.aliases[name]]
                continue
            if i == len(fullpath) - 1 and name in subsection.trait_names(config=True):
                return getattr(subsection, name)
                continue

            msg = f"Could not resolve key '{key}'"
            suggestions = subsection.keys(subsections=True, aliases=True)
            if (suggestion := did_you_mean(suggestions, name)) is not None:
                suggestion_fullkey = ".".join([*fullpath[:i], suggestion])
                msg += f" (did you mean '{suggestion_fullkey}'?)"

            raise KeyError(msg)

        return subsection

    def __contains__(self, key: str) -> bool:
        """Return if key leads to an existing subsection or trait."""
        return key in self.keys(subsections=True, aliases=True)

    def __iter__(self) -> Iterator[str]:
        """Iterate over possible keys.

        Simply iter :meth:`keys`.
        """
        return iter(self.keys())

    def __len__(self) -> int:
        """Return number of valid keys."""
        return len(list(self.keys()))

    def __eq__(self, other: Any) -> bool:
        """Check equality with other section.

        If *other* is not a Section, will return False. Both section must have the same
        keys and same values.
        """
        if not isinstance(other, Section):
            return False
        # Check that we have the same keys
        if set(self.keys()) != set(other.keys()):
            return False
        return dict(self) == dict(other)

    def __ne__(self, other: Any) -> bool:
        return not self == other

    # - end of Mapping methods
    # - Mutable Mapping methods

    def __setitem__(self, key: str, value: Any) -> None:
        """Set a trait to a value.

        Parameters
        ----------
        key
            Path to leading to a trait.
        """
        *prefix, trait_name = key.split(".")
        if len(prefix) == 0:
            subsection = self
        else:
            subsection = self[".".join(prefix)]

        if trait_name not in subsection.trait_names():
            msg = f"Could not resolve key '{key}'"
            suggestions = subsection.keys(recursive=False)
            if (suggestion := did_you_mean(suggestions, trait_name)) is not None:
                suggestion_fullkey = ".".join([*prefix, suggestion])
                msg += f" (did you mean '{suggestion_fullkey}'?)"
            raise KeyError(msg)

        setattr(subsection, trait_name, value)

    def setdefault(
        self,
        key: str,
        default: TraitType | None = None,
        value: Any | Sentinel = Undefined,
    ) -> Any:
        """Set a trait to a value if it exists.

        If the trait exists, return its value. Otherwise, the *default* argument must be
        provide a trait instance to add it to the section, it is set to *value* if it is
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
                f"Key '{key}' does not exist. To add a trait there, a TraitType has to "
                "be passed to `default`."
            )
        self.add_trait(key, default)
        if value is not Undefined:
            self[key] = value

        return self[key]

    def pop(self, key: str, other: Any | None = None) -> Any:
        """Sections do not support the *pop* operation.

        A trait cannot be deleted.
        """
        raise TypeError("Sections do not support 'pop'. A trait cannot be deleted")

    def popitem(self) -> tuple[str, Any]:
        """Sections do not support the *popitem* operation.

        A trait cannot be deleted.
        """
        raise TypeError("Sections do not support 'popitem'. A trait cannot be deleted")

    def clear(self) -> None:
        """Sections do not support the *clear* operation.

        A trait cannot be deleted. You may use :meth:`reset` to reset all traits to
        their default value.
        """
        raise TypeError(
            "Sections do not support 'clear'. A trait cannot be deleted. "
            "You may use 'reset' to reset all traits to their default value."
        )

    def reset(self) -> None:
        """Reset all traits to their default value."""
        for name, trait in self.traits(config=True).items():
            self[name] = trait.default()

        for subsection in self.subsections().values():
            subsection.reset()

    def update(
        self,
        other: Section | Mapping[str, Any] | None = None,
        allow_new: bool = False,
        **kwargs: Any,
    ) -> None:
        """Update values of this Section traits.

        This does not block trait notification. This must be done manually for all
        the relevant sections.

        Parameters
        ----------
        other
            Other Section to take traits values from (recursively). It can also be a
            flat mapping of full path keys (``"some.path.to.trait"``) to values or
            trait instances, which default value will be used.
        allow_new
            If True, allow creating new traits for this Section. If `other` is a section
            the trait is copied over; in a mapping it must be a trait instance which
            default value will be used. Default is False.
        kwargs
            Same as `other`.
        """
        input_section = False
        values: dict[str, Any]
        if other is None:
            values = {}
        elif isinstance(other, Section):
            values = dict(other)
            input_section = True
        else:
            values = dict(other)
        values |= kwargs

        for key, value in values.items():
            if key not in self:
                if not allow_new:
                    raise KeyError(
                        f"Trait '{key}' does not exist in {self} "
                        "and trait creation was not authorized."
                    )

                if isinstance(value, TraitType):
                    newtrait = value
                elif input_section:
                    newtrait = other.traits_recursive()[key]  # type: ignore[union-attr]
                else:
                    raise TypeError(
                        "A new trait must be specified as a TraitType or from a Section "
                        f"({key}: {type(value)})"
                    )

                self.add_trait(key, newtrait)

            # trait exists or has been added
            if isinstance(value, TraitType):
                value = value.default()

            self[key] = value

    # - end of Mutable Mapping methods

    def add_trait(
        self, key: str, trait: TraitType, allow_recursive: bool = True
    ) -> None:
        """Add a trait to this section or one of its subsection.

        The trait name cannot be already in use.

        Parameters
        ----------
        key
            Path of dot separated attribute names leading to the trait to add. It can
            also only be a trait name to add to *this* section.
        trait
            Trait instance to add.
        allow_recursive
            If True (default), subsections specified in *key* that are not contained in
            this section will be added automatically. Otherwise, this will raise on
            unknown subsections in *key*.
        """
        *prefix, trait_name = key.split(".")

        section = self
        for name in prefix:
            if name in section._subsections:
                pass
            # subsection does not exist
            elif allow_recursive:
                empty: type[Section] = type("AutoGeneratedSection", (Section,), {})
                empty_descr = Subsection(empty)

                # Register subsection
                section._subsections[name] = empty_descr
                # Set up Subsection descriptor
                empty_descr.__set_name__(section.__class__, name)
                setattr(section.__class__, name, empty_descr)
                # Assign new instance
                setattr(section, name, empty())
                # Set instance attributes
                subsection_inst = getattr(section, name)
                subsection_inst._name = name
                subsection_inst._parent = section
            else:
                raise KeyError(
                    f"There is no section '{name}', and creating subsections "
                    f"to add trait '{key}' was not allowed."
                )

            # section exists or has been added
            section = getattr(section, name)

        if trait_name in section.trait_names():
            raise KeyError(f"Trait '{key}' already exists.")

        section.add_traits(**{trait_name: trait})
        # need to update subsection class in parent
        if (parent := section._parent) is not None:
            parent._subsections[section._name].klass = section.__class__

    def as_dict(
        self, recursive: bool = True, aliases: bool = False, nest: bool = False
    ) -> dict[str, Any]:
        """Return traits as a dictionary.

        Parameters
        ----------
        recursive
            If True (default), return parameters from all subsections. Otherwise limit to
            only this section.
        aliases
            If True, include aliases. Default is False.
        nest
            If True return a nested dictionnary. Otherwise return a flat dictionnary
            with dot-separated keys. Default is False.
        """
        output = dict(
            self.items(subsections=False, recursive=recursive, aliases=aliases)
        )
        if nest:
            output = self.nest_dict(output)
        return output

    def select(self, *keys: str, nest: bool = False) -> dict[str, Any]:
        """Select parameters from this sections or its subsections.

        Parameters
        ----------
        keys
            Keys leading to parameters. To select parameters from subsections, use
            dot-separated syntax like ``"some.nested.parameter"``.
        nest
            If True return a nested dictionnary. Otherwise return a flat dictionnary
            with dot-separated keys. Default is False.
        """
        output = {k: self[k] for k in keys}
        if nest:
            output = self.nest_dict(output)
        return output

    @overload
    @classmethod
    def _iter_traits(
        cls,
        subsections: Literal[False],
        recursive: bool = ...,
        aliases: bool = ...,
        own_traits: bool = ...,
        **metadata: Any,
    ) -> Generator[tuple[str, TraitType]]: ...

    @overload
    @classmethod
    def _iter_traits(
        cls,
        subsections: bool = ...,
        recursive: bool = ...,
        aliases: bool = ...,
        own_traits: bool = ...,
        **metadata: Any,
    ) -> Generator[tuple[str, TraitType | type[Section]]]: ...

    @classmethod
    def _iter_traits(
        cls,
        subsections: bool = False,
        recursive: bool = True,
        aliases: bool = False,
        own_traits: bool = False,
        **metadata: Any,
    ) -> Generator[tuple[str, TraitType | type[Section]]]:
        """Iterate over keys and traits.

        Traits are identical for class and instances. This method is thus used by
        class_traits_recursive, traits_recursive and keys.

        Parameters
        ----------
        subsections
            If True (default is False), keys can map to subsections classes.
        recursive
            If True (default), return parameters from all subsections. Otherwise limit to
            only this section.
        aliases
            If True (default is False), include aliases.
        own_traits:
            If True do not list traits from parent classes. Default to False.
        """
        traits = (
            cls.class_own_traits(**metadata)
            if own_traits
            else cls.class_traits(**metadata)
        )
        traits = {k: v for k, v in traits.items() if not k.startswith("_")}
        yield from traits.items()

        subs = dict(cls.class_subsections())
        if aliases:
            for shortcut, alias in cls.aliases.items():
                target = cls
                for subname in alias.split("."):
                    target = target._subsections[subname].klass
                subs[shortcut] = target

        for name, subsection in subs.items():
            if subsections:
                yield name, subsection
            if recursive:
                subtraits = subsection._iter_traits(
                    subsections=subsections,
                    recursive=True,
                    aliases=aliases,
                    own_traits=own_traits,
                    **metadata,
                )
                yield from ((f"{name}.{k}", v) for k, v in subtraits)

    @classmethod
    def traits_recursive(
        cls, nest: bool = False, aliases: bool = False, **metadata: Any
    ) -> dict[str, TraitType]:
        """Return dictionnary of all traits."""
        traits = dict(cls._iter_traits(subsections=False, aliases=aliases, **metadata))
        if nest:
            traits = cls.nest_dict(traits)
        return traits

    @classmethod
    def defaults_recursive(
        cls, nest: bool = False, aliases: bool = False, **metadata: Any
    ) -> dict[str, Any]:
        """Return nested dictionnary of default traits values."""
        traits = cls._iter_traits(subsections=False, aliases=aliases, **metadata)
        defaults = {k: t.default() for k, t in traits}
        if nest:
            defaults = cls.nest_dict(defaults)
        return defaults

    @classmethod
    def class_subsections(cls) -> dict[str, type[Section]]:
        """Iterate over subsections types."""
        return {name: descr.klass for name, descr in cls._subsections.items()}

    def subsections(self) -> dict[str, Section]:
        """Iterate over subsections instances."""
        return {name: getattr(self, name) for name in self._subsections}

    @classmethod
    def class_subsections_recursive(cls) -> Iterator[type[Section]]:
        """Iterate recursively over all subsections types."""
        yield cls
        for subsection in cls.class_subsections().values():
            yield from subsection.class_subsections_recursive()

    def subsections_recursive(self) -> Iterator[Section]:
        """Iterate recursively over all subsections instance."""
        yield self
        for subsection in self.subsections().values():
            yield from subsection.subsections_recursive()

    @classmethod
    def nest_dict(cls, flat: Mapping[str, Any]) -> dict[str, Any]:
        """Nest a dictionnary according to the structure of this section."""
        nested: dict[str, Any] = {}
        for key, val in flat.items():
            subconf = nested
            section = cls
            *subkeys, trait = key.split(".")
            for subkey in subkeys:
                subconf = subconf.setdefault(subkey, {})
                if subkey in section._subsections:
                    section = section._subsections[subkey].klass
                elif subkey in section.aliases:
                    for subalias in section.aliases[subkey].split("."):
                        section = section._subsections[subalias].klass
                else:
                    raise KeyError(
                        f"Invalid key '{key}', '{subkey}' is not a subsection or alias."
                    )
            if trait not in section.class_trait_names():
                raise KeyError(f"Invalid key '{key}', '{trait}' is not a trait.")
            subconf[trait] = val
        return nested

    @classmethod
    def flatten_dict(cls, nested: Mapping[str, Any]) -> dict[str, Any]:
        """Flatten a dictionnary according to the structure of this section."""
        flat: dict[str, Any] = {}

        def recurse(d: Mapping, fullpath: list[str], section: type[Section]) -> None:
            if not isinstance(d, Mapping):
                raise KeyError(
                    f"{'.'.join(fullpath)} corresponds to a subsection, "
                    f"it should be a Mapping (received {type(d)})."
                )
            for key, val in d.items():
                newpath = fullpath + [key]
                fullkey = ".".join(newpath)
                if key in section._subsections:
                    recurse(val, newpath, section._subsections[key].klass)
                    continue
                if key in section.aliases:
                    for subalias in section.aliases[key].split("."):
                        section = section._subsections[subalias].klass
                    recurse(val, newpath, section)
                    continue
                if key not in section.class_trait_names():
                    raise KeyError(f"{fullkey} is not a trait.")
                flat[fullkey] = val

        recurse(nested, [], cls)
        return flat

    @classmethod
    def resolve_key(cls, key: str | list[str]) -> tuple[str, type[Section], TraitType]:
        """Resolve a key.

        Parameters
        ----------
        key
            Dot separated (or a list of) attribute names that point to a trait in the
            configuration tree, starting from this Section.
            It might contain aliases/shortcuts.

        Returns
        -------
        fullkey
            Dot separated attribute names that *unambiguously* and *uniquely* point to a
            trait in the config tree, starting from this Section, ending with the trait
            name.
        subsection
            The :class:`Section` *class* that contains the trait.
        trait
            The :class:`trait<traitlets.TraitType>` object corresponding to the key.
        """
        if isinstance(key, str):
            key = key.split(".")

        *prefix, trait_name = key
        fullkey = []
        subsection = cls
        for subkey in prefix:
            if subkey in subsection._subsections:
                subsection = subsection._subsections[subkey].klass
                fullkey.append(subkey)
            elif subkey in cls.aliases:
                alias = cls.aliases[subkey].split(".")
                fullkey += alias
                for alias_subkey in alias:
                    subsection = subsection._subsections[alias_subkey].klass
            else:
                secname = ".".join(fullkey) + " " if fullkey else ""
                secname += f"({get_classname(subsection)})"
                raise UnknownConfigKeyError(
                    f"Section {secname} has no subsection or alias '{subkey}'."
                )

        if trait_name not in subsection.class_trait_names(config=True, subsection=None):
            secname = ".".join(fullkey) + " " if fullkey else ""
            secname += f"({get_classname(subsection)})"
            raise UnknownConfigKeyError(
                f"Section {secname} has no trait '{trait_name}'."
            )

        trait = getattr(subsection, trait_name)

        return ".".join(fullkey + [trait_name]), subsection, trait

    @staticmethod
    def merge_configs(
        *configs: Mapping[str, ConfigValue],
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

    @classmethod
    def help(cls) -> None:
        """Print description of this section and its traits."""
        print("\n".join(cls.emit_help()))

    @classmethod
    def emit_help(cls, fullpath: list[str] | None = None) -> list[str]:
        """Return help for this section, and its subsections recursively.

        Contains the name of this section, its description if it has one, eventual
        aliases/shortcuts, help on each trait, and same thing recursively on subsections.

        Format the help so that it can be used as help for specifying values from the
        command line.
        """
        if fullpath is None:
            fullpath = []

        title = cls.__name__
        if fullpath:  # we are not at root
            title = f"{'.'.join(fullpath)} ({title})"
        lines = [title]
        underline(lines)

        description = cls.emit_description()
        if description:
            lines += description
            lines.append("")

        # aliases
        if cls.aliases:
            add_spacer(lines)
            lines.append("Aliases:")
            underline(lines)
            for short, long in cls.aliases.items():
                lines.append(f"{short}: {long}")

        for name, trait in cls.class_traits(config=True).items():
            lines += indent(
                cls.emit_trait_help(fullpath + [name], trait), initial_indent=False
            )

        for name, subsection in cls.class_subsections().items():
            add_spacer(lines)
            lines += subsection.emit_help(fullpath + [name])

        return lines

    @classmethod
    def emit_description(cls) -> list[str]:
        """Return lines of description of this section.

        Take the section docstring if defined, and format it nicely (wraps it, remove
        trailing whitespace, etc.). Return a list of lines.
        """
        doc = cls.__doc__
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

    @classmethod
    def emit_trait_help(cls, fullpath: list[str], trait: TraitType) -> list[str]:
        """Return lines of help for a trait of this section.

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

    def values_from_func_signature(
        self, func: Callable, trait_select: Mapping | None = None, **kwargs: Any
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


MutableMapping[str, Any].register(Section)

_HasTraits = TypeVar("_HasTraits", bound=HasTraits)


def tag_all_traits(**metadata: Any) -> Callable[[type[_HasTraits]], type[_HasTraits]]:
    """Tag all class-own traits.

    Do not replace existing tags.

    Parameters
    ----------
    metadata:
        Are passed to ``trait.tag(**metadata)``.
    """

    def decorator(cls: type[_HasTraits]) -> type[_HasTraits]:
        for trait in cls.class_own_traits().values():
            for key, value in metadata.items():
                if key not in trait.metadata:
                    trait.tag(**{key: value})
        return cls

    return decorator
