"""Section: nested equivalent of Configurable.

Defines a :class:`Section` class meant to be used in place of
:class:`traitlets.config.Configurable` that make possible deeply nested configurations.
"""

from __future__ import annotations

import itertools
import logging
import typing as t
from collections import abc
from inspect import Parameter, signature
from textwrap import dedent

from traitlets import Enum, Instance, Sentinel, TraitType, Undefined
from traitlets.config import HasTraits

from .loaders import ConfigValue
from .util import (
    UnknownConfigKeyError,
    add_spacer,
    get_trait_typehint,
    indent,
    nest_dict,
    stringify,
    underline,
    wrap_text,
)

if t.TYPE_CHECKING:
    from .application import ApplicationBase

log = logging.getLogger(__name__)


S = t.TypeVar("S", bound="Section")


def subsection(section: type[S]) -> Instance[S]:
    """Transform a subsection class into a proper trait.

    To make the specification easier, an attribute of type :class:`Section` will
    automatically be transformed into a proper :class:`Instance` trait using this
    function. It can be used "manually" as well, this will most notably help static
    type checkers understand what is happening.

    So when specifying a subsection the two lines below are equivalent::

        sub_name = MySubSection
        sub_name = subsection(MySubSection)

    """
    return Instance(section, args=(), kw={}).tag(subsection=True, config=False)


def _name_to_classdef(name: str) -> str:
    return f"_{name}SectionDef"


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
      *subsection* and replaced by a :class:`traitlets.Instance` trait, tagged as a
      "subsection" in its metadata.
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

    _application_cls: type[ApplicationBase] | None = None

    _subsections: dict[str, type[Section]] = {}
    """Mapping of nested Section classes."""

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

    def __init_subclass__(cls, /, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._setup_section()

    @classmethod
    def _setup_section(cls) -> None:
        """Set up the class after definition.

        This hook is run in :meth:`__init_subclass__`, after any subclass of
        :class:`Section` is defined.

        By default, deals with the objective of Section: tagging all traits as
        configurable, and setting up attributes that are subclasses of Section
        as :class:`~traitlets.Instance` traits, and registering them as subsections.

        This method can be modified by subclasses in need of specific behavior. Do not
        forget to call the ``super()`` version, and if traits are added/modified it
        might be necessary to call :meth:`traitlets.traitlets.HasTraits.setup_class`
        (``cls.setup_class(cls.__dict__)``).
        """
        cls._subsections = {}
        classdict = cls.__dict__

        to_add: dict[str, type[Section]] = {}

        for k, v in classdict.items():
            # tag traits as configurable
            if isinstance(v, TraitType):
                if v.metadata.get("config", True):
                    v.tag(config=True)

            if not cls._dynamic_subsections:
                continue

            # Add Section definitions
            if isinstance(v, type) and issubclass(v, Section) and k == v.__name__:
                to_add[k.rstrip("_")] = v

        for k, v in to_add.items():
            # change location of class definition
            new_name = _name_to_classdef(k)
            v.__name__ = new_name
            v.__qualname__ = f"{cls.__qualname__}.{new_name}"
            setattr(cls, new_name, v)

            # And add a subsection
            setattr(cls, k, subsection(v))

        # add ancestors subsections
        for base in cls.__bases__:
            if issubclass(base, Section):
                cls._subsections |= base._subsections

        # register new subsections
        for k, v in classdict.items():
            if isinstance(v, Instance):
                # if v.klass is str, transform to corresponding type
                v._resolve_classes()
                assert isinstance(v.klass, type)  # maybe into a try/except block?
                if issubclass(v.klass, Section):
                    cls._subsections[k] = v.klass
                    v.tag(subsection=True, config=False)

        cls.setup_class(classdict)  # type: ignore

        # Check aliases
        for short, alias in cls.aliases.items():
            subsection_cls = cls
            for key in alias.split("."):
                try:
                    subsection_cls = subsection_cls._subsections[key]
                except KeyError as err:
                    raise KeyError(
                        f"Alias '{short}:{alias}' in {cls.__name__} malformed."
                    ) from err

    def __init__(
        self,
        config: abc.Mapping[str, t.Any] | None = None,
        *,
        app: ApplicationBase | t.Literal[False] | None = None,
        **kwargs,
    ):
        clsname = self.__class__.__name__

        if config is None:
            config = {}
        config = dict(config)

        if app is not False:
            if app is None and self._application_cls is not None:
                app = self._application_cls.instance()
            if app is not None:
                if clsname not in app._separate_sections:
                    raise KeyError(f"'{clsname}' is not among registered sections.")

                app_conf: dict[str, t.Any] = nest_dict(app.conf).get(clsname, {})
                config = app_conf | config

        config |= kwargs

        with self.hold_trait_notifications():
            self._init_subsections(config)
            self._init_direct_traits(config)

        if config:
            raise KeyError(f"Extra parameters for {clsname} {list(config.keys())}")

        self.postinit()

    def _init_direct_traits(self, config: dict[str, t.Any], **kwargs):
        config |= kwargs

        log.info("instanciate %s with %s", self.__class__.__name__, config)
        for name in self.trait_names(config=True, subsection=None):
            if name in config:
                value = config.pop(name)
                if isinstance(value, ConfigValue):
                    value = value.get_value()
                setattr(self, name, value)

    def _init_subsections(self, config: dict[str, t.Any], **kwargs):
        config |= kwargs
        for name, subcls in self._subsections.items():
            sub_inst = subcls(config.pop(name, {}))
            setattr(self, name, sub_inst)

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
        branch_subsection = "\u251d" + "\u2501" * len(line) + "\u2511"
        elbow_subsection = "\u2515" + "\u2501" * len(line) + "\u2511"
        pipe = "\u2502" + " " * len(line)
        blank = " " * len(pipe)

        lines = [self.__class__.__name__]
        traits = self.traits(config=True, subsection=None)
        for i, (key, trait) in enumerate(traits.items()):
            symb = branch
            if i == len(traits) - 1 and not self._subsections:
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

        for i, name in enumerate(self._subsections):
            lines.append(header + pipe)
            is_last = i == len(self._subsections) - 1

            subsection: Section = getattr(self, name)
            sublines = subsection._get_lines(header + (blank if is_last else pipe))

            symb = elbow_subsection if is_last else branch_subsection
            sublines[0] = f"{header}{symb}{name}:"
            lines += sublines

        return lines

    def __dir__(self):
        if not self._attr_completion_only_traits:
            return super().__dir__()
        configurables = set(self.trait_names(config=True))
        subsections = set(self._subsections.keys())
        return configurables | subsections

    # - Mapping methods

    def keys(
        self, subsections: bool = False, recursive: bool = True, aliases: bool = False
    ) -> list[str]:
        """Return iterable of keys leading to subsections and traits.

        Parameters
        ----------
        subsections
            If True (default is False), keys can lead to subsections instances.
        recursive
            If True (default), return keys for parameters from all subsections.
        aliases
            If True (default is False), include aliases.
        """
        return list(
            self._keys(subsections=subsections, recursive=recursive, aliases=aliases)
        )

    def _keys(
        self, subsections: bool = False, recursive: bool = True, aliases: bool = False
    ) -> abc.Generator[str]:
        trait_names = self.trait_names(subsection=None, config=True)
        yield from filter(lambda s: not s.startswith("_"), trait_names)

        subs: list[abc.Iterable] = [self._subsections]
        if aliases:
            subs.append(self.aliases.keys())

        for name in itertools.chain(*subs):
            subsection = self[name]
            if subsections:
                yield name
            if recursive:
                sub_traits = subsection.keys(subsections=subsections, aliases=aliases)
                yield from (f"{name}.{s}" for s in sub_traits)

    def values(
        self, subsections: bool = False, recursive: bool = True, aliases: bool = False
    ) -> list[t.Any]:
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
    ) -> list[tuple[str, t.Any]]:
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

    def get(self, key: str, default: t.Any | None = None) -> t.Any:
        """Obtain value at `key`."""
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: str) -> t.Any:
        """Obtain value it `key`."""
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
            raise KeyError(
                f"Could not resolve key {key} "
                f"('{name}' not in {subsection.__class__.__name__})"
            )

        return subsection

    def __contains__(self, key: str) -> bool:
        """Return if key leads to an existing subsection or trait."""
        return key in self.keys(subsections=True, aliases=True)

    def __iter__(self) -> abc.Iterable[str]:
        """Iterate over possible keys.

        Simply iter :meth:`keys`.
        """
        return iter(self.keys())

    def __len__(self) -> int:
        """Return number of valid keys."""
        return len(list(self.keys()))

    def __eq__(self, other: t.Any) -> bool:
        """Check equality with other section.

        If *other* is not a Section, will return False. Both section must have the same
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
            subsection = self
        else:
            subsection = self[".".join(prefix)]

        if trait_name not in subsection.trait_names():
            clsname = subsection.__class__.__name__
            raise KeyError(f"No trait '{trait_name}' in section {clsname}.")

        setattr(subsection, trait_name, value)

    def setdefault(
        self,
        key: str,
        default: TraitType | None = None,
        value: t.Any | Sentinel = Undefined,
    ) -> t.Any:
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
                f"Key '{key}' does not exist. A trait argument must be "
                " supplied to be added to the section."
            )
        self.add_trait(key, default)
        if value is not Undefined:
            self[key] = value

        return self[key]

    def pop(self, key: str, other: t.Any | None = None) -> t.Any:
        """Sections do not support the *pop* operation.

        A trait cannot be deleted.
        """
        raise TypeError("Sections do not support 'pop'. A trait cannot be deleted")

    def popitem(self) -> tuple[str, t.Any]:
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

        def func(section: Section, traits, key: str, trait: TraitType, path):
            setattr(section, key, trait.default())

        self.remap(func, config=True)

    def update(
        self,
        other: Section | abc.Mapping[str, t.Any] | None = None,
        allow_new: bool = False,
        raise_on_miss: bool = False,
        **kwargs,
    ):
        """Update values of this Section traits.

        Some trait that do not exist in this instance, but are specified can be added.
        Currently whole subsections cannot be added.

        Parameters
        ----------
        other
            Other Section to take traits values from (recursively). It can also be a
            flat mapping of full path keys (``"some.path.to.trait"``) to values or
            trait instances, which default value will be used.
        allow_new
            If True, allow creating new traits for this Section. A new trait must can be
            a trait in `other` if it is a Section; in a mapping it must be a trait
            instance which default value will be used. Default is False.
        raise_on_miss
            If True, raise an exception if a trait in `other` is placed on a path that
            does not lead to an existing subsection or trait. Default is False.
        kwargs
            Same as `other`.
        """
        input_section = False
        values: dict[str, t.Any]
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
                if raise_on_miss:
                    raise KeyError(f"Trait '{key}' does not exist in {self}")
                if not allow_new:
                    raise RuntimeError(f"Trait creation was not authorized ({key})")

                if isinstance(value, TraitType):
                    newtrait = value
                elif input_section:
                    newtrait = other.traits_recursive(flatten=True)[key]  # type: ignore[union-attr]
                else:
                    raise TypeError(
                        "A new trait must be specified as a TraitType or from a Section "
                        f"({key}: {type(value)})"
                    )

                self.add_trait(key, newtrait)

            # trait exists or has been added
            if isinstance(value, TraitType):
                value = value.default

            self[key] = value

    # - end of Mutable Mapping methods

    def add_trait(self, key: str, trait: TraitType, allow_recursive: bool = True):
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
                section.add_traits(**{name: subsection(Section)})
                section._subsections[name] = Section
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

    def as_dict(
        self, recursive: bool = True, aliases: bool = False, flatten: bool = True
    ) -> dict[str, t.Any]:
        """Return traits as a dictionary.

        Parameters
        ----------
        recursive
            If True (default), return parameters from all subsections. Otherwise limit to
            only this section.
        aliases
            If True (default is False), include aliases.
        flatten
            If True (default), return a flat dictionnary with dot-separated keys.
            Otherwise return a nested dictionnary.
        """
        output = dict(
            self.items(subsections=False, recursive=recursive, aliases=aliases)
        )
        if not flatten:
            output = nest_dict(output)
        return output

    def select(self, *keys: str, flatten: bool = False) -> dict[str, t.Any]:
        """Select parameters from this sections or its subsections.

        Parameters
        ----------
        keys
            Keys leading to parameters. To select parameters from subsections, use
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
    def _subsections_recursive(cls) -> abc.Iterator[type[Section]]:
        """Iterate recursively over all subsections."""
        for subsection in cls._subsections.values():
            yield from subsection._subsections_recursive()
        yield cls

    @classmethod
    def class_traits_recursive(cls) -> dict:
        """Return nested/recursive dict of all traits."""
        config: dict[t.Any, t.Any] = dict()
        config.update(cls.class_own_traits(config=True))
        for name, subsection in cls._subsections.items():
            config[name] = subsection.class_traits_recursive()
        return config

    # Lifted from traitlets.config.application.Application
    @classmethod
    def _classes_inc_parents(
        cls, classes: abc.Iterable[type[Section]] | None = None
    ) -> abc.Generator[type[Section], None, None]:
        """Iterate through configurable classes, including configurable parents.

        Children should always be after parents, and each class should only be
        yielded once.

        Parameters
        ----------
        classes
            The list of classes to start from; if not set, uses all nested subsections.
        """
        if classes is None:
            classes = cls._subsections_recursive()

        seen = set()
        for c in classes:
            # We want to sort parents before children, so we reverse the MRO
            for parent in reversed(c.mro()):
                if issubclass(parent, Section) and (parent not in seen):
                    seen.add(parent)
                    yield parent

    def remap(
        self,
        func: abc.Callable[[Section, dict, str, TraitType, list[str]], None] | None,
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
            path of subsection leading to a trait, separated by dots (ie
            ``"some.path.to.trait"``). Default is False.
        metadata:
            Select only some traits which metadata satistify this argument.
        """

        def recurse(section: Section, outsec: dict, path: list[str]):
            for name, trait in section.traits(**metadata, subsection=None).items():
                fullpath = path + [name]
                key = ".".join(fullpath) if flatten else name
                outsec[key] = trait
                if func is not None:
                    func(section, outsec, key, trait, fullpath)

            for name in section._subsections:
                if flatten:
                    sub_outsec = outsec
                else:
                    outsec[name] = {}
                    sub_outsec = outsec[name]

                recurse(getattr(section, name), sub_outsec, path + [name])

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
    def resolve_key(cls, key: str | list[str]) -> tuple[str, type[Section], TraitType]:
        """Resolve a key.

        This method is meant to be used pre-instanciation.

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
                subsection = subsection._subsections[subkey]
                fullkey.append(subkey)
            elif subkey in cls.aliases:
                alias = cls.aliases[subkey].split(".")
                fullkey += alias
                for alias_subkey in alias:
                    subsection = subsection._subsections[alias_subkey]
            else:
                raise UnknownConfigKeyError(
                    f"Section '{'.'.join(fullkey)}' ({_subsection_clsname(subsection)}) "
                    f"has no subsection or alias '{subkey}'."
                )

        if not hasattr(subsection, trait_name):
            raise UnknownConfigKeyError(
                f"Section '{'.'.join(fullkey)}' ({_subsection_clsname(subsection)}) "
                f"has no trait '{trait_name}'."
            )
        trait = getattr(subsection, trait_name)

        return ".".join(fullkey + [trait_name]), subsection, trait

    @staticmethod
    def merge_configs(
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
        """Print description of this section and its traits."""
        print("\n".join(self.emit_help()))

    def emit_help(self, fullpath: list[str] | None = None) -> list[str]:
        """Return help for this section, and its subsections recursively.

        Contains the name of this section, its description if it has one, eventual
        aliases/shortcuts, help on each trait, and same thing recursively on subsections.

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

        for name in sorted(self._subsections):
            add_spacer(lines)
            lines += getattr(self, name).emit_help(fullpath + [name])

        return lines

    def emit_description(self) -> list[str]:
        """Return lines of description of this section.

        Take the section docstring if defined, and format it nicely (wraps it, remove
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


def _subsection_clsname(section: type[Section] | Section, module: bool = True) -> str:
    if not isinstance(section, type):
        section = section.__class__

    mod = ""
    if module:
        try:
            mod = section.__module__
        except AttributeError:
            pass

    try:
        name = section.__qualname__
    except AttributeError:
        return str(section)

    return ".".join([mod, name])


abc.MutableMapping[str, t.Any].register(Section)
