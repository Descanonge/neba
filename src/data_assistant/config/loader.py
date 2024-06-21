"""Configuration loaders.

Similarly to traitlets, the
:class:`Application<data_assistant.config.application.ApplicationBase>` object delegates
the work of loading configuration values from various sources (config files, CLI, etc.).

Because we want to allow nested configurations, the traitlets loaders are not really
appropriate and difficult to adapt. Therefore we start from scratch (but still borrowing
some code...).

The application will try to make sense of the configuration it receives from the loader.
It should raise on any malformed or invalid config key, but the loader can still act
upstream, for instance on duplicate keys.

Presently, the application accepts different
types of keys:

* "fullpaths": they define the succession of attribute names leading to a specific
  trait (example ``group.subgroup.sub_subgroup.trait_name``)
* "fullpaths with shortcuts": :class:`schemes<data_assistant.config.scheme.Scheme>` can
  define shortcuts to avoid repeating parts of the fullpath (for example we could have a
  key ``shortcut.trait_name`` that would be equivalent to the one above).
* "class keys": they use the :class:`~.config.scheme.Scheme` class name followed by that
  of a trait (for example ``SchemeClassName.trait_name``). Since we allow a scheme to be
  re-used multiple times in the nested configuration, this can be equivalent to
  specifying multiple parameters with the same values. They will have a lower priority
  than specifying the full path.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import typing as t
from argparse import Action, ArgumentParser, _AppendAction
from collections import abc
from os import path
from textwrap import dedent

from traitlets.traitlets import Container, Enum, HasTraits, TraitError, TraitType, Union
from traitlets.utils.sentinel import Sentinel

from .util import (
    ConfigError,
    ConfigErrorHandler,
    ConfigParsingError,
    MultipleConfigKeyError,
    flatten_dict,
    get_trait_typehint,
    nest_dict,
    underline,
    wrap_text,
)

if t.TYPE_CHECKING:
    from tomlkit.container import Container as TOMLContainer
    from tomlkit.container import Item, Table

    from .application import ApplicationBase
    from .scheme import Scheme

    T = t.TypeVar("T", bound=TOMLContainer | Table)


_DOT = "__DOT__"
"""String replacement for dots in command line keys."""


Undefined = Sentinel(
    "Undefined", "data-assistant", "Configuration value not (yet) set or parsed."
)
""":class:`traitlets.Sentinel<traitlets.utils.sentinel.Sentinel>` object for undefined configuration values.

Allows to separate them from simply ``None``.
"""  # noqa: E501


class ConfigValue:
    """Value obtained from a source.

    It stores a number of information about the value (its origin, initial value, etc.).

    Parameters
    ----------
    input
        The initial value obtained from a configuration source.
    key
        The key it was associated with in the source. For information purpose mainly.
    origin
        A string specifying the configuration source it was found in. For information
        purpose mainly.
    """

    def __init__(self, input: t.Any, key: str, origin: str | None = None):
        if isinstance(input, list):
            if len(input) == 1:
                input = input[0]

        self.key = key
        """The key this value was associated to."""
        self.input = input
        """The initial value obtained."""
        self.origin = origin
        """A description of the configuration source it was found in."""

        self.value: t.Any = Undefined
        """The parameter value once parsed.

        By default, it equals to :attr:`Undefined`.
        """
        self.trait: TraitType | None = None
        """The trait instance specifying the parameter to configure."""
        self.container_cls: type[HasTraits] | None = None
        """The configurable class that owns the trait."""
        self.priority: int = 100
        """Priority of the value used when merging config.

        If two values, possibly from different sources, target the same parameter the
        value with the highest priority is used.
        """

    def __str__(self) -> str:
        s = [str(self.get_value())]
        if self.origin is not None:
            s.append(f"({self.origin})")
        return " ".join(s)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)})"

    def copy(self, **kwargs) -> t.Self:
        """Return a copy of this instance.

        Parameters
        ----------
        kwargs
            Attribute values to overwrite in the copy.
        """
        data = {
            attr: getattr(self, attr)
            for attr in [
                "key",
                "origin",
                "value",
                "trait",
                "trait",
                "container_cls",
                "priority",
            ]
        }
        data |= kwargs

        out = self.__class__(self.input, self.key)
        for attr, value in data.items():
            setattr(out, attr, value)
        return out

    def get_value(self) -> t.Any:
        """Return the actual value to use as parameter.

        By default, use the :attr:`value` attribute, unless it is :attr:`Undefined` then
        use the initial value (possibly unparsed).
        """
        if self.value is not Undefined:
            return self.value
        return self.input

    def parse(self) -> None:
        """Parse the initial value.

        Parsing traits is done by either
        :meth:`TraitType.from_string<traitlets.TraitType.from_string>` or
        :meth:`Container.from_string_list<traitlets.Container.from_string_list>` for
        container traits.

        We have to choose the correct function, and :class:`traitlets.Union` traits does
        not do that (if no correct parsing is found it just return the input string, and
        if a correct value is extracted the trait tries to validate it and may fail and
        raise).

        This method tries to handles containers and union more gracefully. If all
        options have been tried and no parsing was successful the function will
        raise.
        """
        if self.trait is None:
            raise ConfigParsingError(
                f"Cannot parse key '{self.key}', has no associated trait."
            )

        def _try(attr: str, trait: TraitType, src: str | list[str]) -> bool:
            try:
                self.value = getattr(trait, attr)(src)
                return True
            except (AttributeError, TraitError, ValueError):
                return False

        def try_item(trait: TraitType, src: str) -> bool:
            return _try("from_string", trait, src)

        def try_list(trait: Container, src: list[str]) -> bool:
            return _try("from_string_list", trait, src)

        def _parse(trait: TraitType, src: str | list[str]) -> bool:
            src = [src] if isinstance(src, str) else src

            # Handle lists
            if isinstance(trait, Container) and try_list(trait, src):
                return True

            # Handle Union with lists
            if isinstance(trait, Union):
                for trait_type in trait.trait_types:
                    if _parse(trait_type, src):
                        return True

            # Handle everything else
            if len(src) == 1 and try_item(trait, src[0]):
                return True

            return False

        if _parse(self.trait, self.input):
            return

        traitname = self.trait.__class__.__name__
        raise ConfigParsingError(
            f"Could not parse '{self.input}' for trait '{self.key}' ({traitname})."
        )


class ConfigLoader:
    """Abstract ConfigLoader.

    Define the public API that will be used by the
    :class:`Application<.application.ApplicationBase>` object, as well as some common
    logic.

    Parameters
    ----------
    app
        Parent application that created this loader.
    log
        Logger instance.
    """

    def __init__(self, app: ApplicationBase, log: logging.Logger | None = None):
        self.app = app
        """Parent application that created this loader.

        It will be used to deal with exceptions, and to resolve/normalize the config
        once loaded.
        """
        if log is None:
            log = logging.getLogger(__name__)
        self.log = log
        self.config: dict[str, ConfigValue] = {}
        """Configuration dictionnary mapping keys to ConfigValues.

        It should be a flat dictionnary.
        """

    def clear(self) -> None:
        """Empty the config."""
        self.config.clear()

    def add(self, key: str, value: ConfigValue):
        """Add key to configuration dictionnary.

        Raises
        ------
        MultipleConfigKeyError
            If the key is already present in the current configuration.
        """
        if key in self.config:
            raise MultipleConfigKeyError(key, [self.config[key], value])
        self.config[key] = value

    def get_config(
        self,
        *args: t.Any,
        apply_application_traits: bool = True,
        resolve: bool = True,
        **kwargs,
    ) -> dict[str, ConfigValue]:
        """Load and return a proper configuration dict.

        This method clears the existing config, call :meth:`load_config` to populate the
        :attr:`config` attribute, apply parameters to the root application,
        resolve/normalize the config and return it.

        Parameters to be applied to the application before proper resolution of the
        whole configuration are detected in a simple manner. Only single level keys and
        class keys corresponding to an existing application trait are used. Aliases not
        yet supported.

        Parameters
        ----------
        args, kwargs
            Passed to :meth:`load_config`.
        """
        self.clear()
        self.load_config(*args, **kwargs)

        if apply_application_traits:
            self.apply_application_traits()

        if resolve:
            self.config = self.app.resolve_config(self.config)

        return self.config

    def apply_application_traits(self) -> None:
        """Apply config for Application."""
        for key, val in self.config.items():
            keypath = key.split(".")
            if (len(keypath) == 1 and key in self.app.trait_names()) or (
                len(keypath) == 2 and keypath[0] == self.app.__class__.__name__
            ):
                traitname = keypath[-1]
                val.trait = self.app.traits()[traitname]
                if val.value is Undefined:
                    val.parse()
                setattr(self.app, traitname, val.get_value())

    def load_config(self, *args, **kwargs) -> None:
        """Populate the config attribute from a source.

        :Not implemented:
        """
        raise NotImplementedError


class DefaultOptionDict(dict[str, Action]):
    """Dictionnary that create missing actions on the fly.

    Meant to replace :attr:`argparse.ArgumentParser._option_string_actions`. Any
    argument not already recognized, and that match the regular expression
    :attr:`option_pattern`, will automatically be assigned an action on the fly by
    :meth:`_create_action` (this static method can be replaced using
    :meth:`_set_action_create`).
    """

    option_pattern = re.compile(r"^--?[A-Za-z_]\w*(\.\w+)*$")
    """Regular expression that unknown argument must match.

    By default, starts with one or two hyphens followed by any number of dot-separated
    words (ie letters, numbers, hyphens, underscores).
    """

    def _add_action(self, key: str) -> None:
        self[key] = self._create_action(key)

    @staticmethod
    def _create_action(key: str) -> Action:
        """Creation an action for the argument ``key``.

        Default action is "append", of type ``str``, with ``nargs=*`` (any number of
        arguments). The destination is the argument name, stripped of leading hyphens,
        with dots "." replaced by :attr:`_DOT` (``__DOT__``) and hyphens replaced by
        underscores.

        Action is "append" to allow to check how many times the user has specified a
        key. This avoids ``--param.one 1 ... --param.one 2`` where the second key
        silently overrides the first value. To obtain a list, simply use it once:
        ``--param.one 1 2``.
        """
        action = _AppendAction(
            option_strings=[key],
            dest=key.lstrip("-").replace("-", "_").replace(".", _DOT),
            type=str,
            nargs="*",
        )
        return action

    @classmethod
    def _set_action_creation(cls, func: abc.Callable[[str], Action]) -> None:
        cls._create_action = staticmethod(func)  # type: ignore

    def __contains__(self, key) -> bool:
        if super().__contains__(key):
            return True

        if self.option_pattern.match(key):
            self._add_action(key)
            return True
        return False

    def __getitem__(self, key) -> Action:
        if key in self:
            return super().__getitem__(key)
        raise KeyError(key)

    def get(self, key, default: t.Any = None) -> t.Any:  # noqa: D102
        try:
            return self[key]
        except KeyError:
            return default


class GreedyArgumentParser(ArgumentParser):
    """Subclass of ArgumentParser that accepts any option."""

    _action_creation_func: abc.Callable[[str], Action] | None = None
    """Callback that will be used to create an action on the fly.

    If None, the default one :meth:`DefaultOptionDict._create_action` will be used.
    """

    def set_action_creation(self, func: abc.Callable[[str], Action]) -> None:
        """Change the default action creation function.

        By using :class:`DefaultOptionDict` unknown arguments will create actions on
        the fly. Replace the default function by ``func``, which must be an unbound
        method or simple function that takes the argument and return an action.
        """
        self._action_creation_func = func

    def parse_known_args(  # type:ignore[override]  # noqa: D102
        self,
        args: abc.Sequence[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> tuple[argparse.Namespace | None, list[str]]:
        # must be done immediately prior to parsing because if we do it in init,
        # registration of explicit actions via parser.add_option will fail during setup

        # Setup defaultdict
        defaultdict_class = DefaultOptionDict
        if self._action_creation_func is not None:
            defaultdict_class._set_action_creation(self._action_creation_func)

        for container in (self, self._optionals):
            container._option_string_actions = defaultdict_class(
                container._option_string_actions
            )
        return super().parse_known_args(args, namespace)


class CLILoader(ConfigLoader):
    """Load config from command line.

    This uses the standard module :mod:`argparse`. However, rather than specifying
    each and every possible argument (there is many possibilities because of the keys
    allowed by the application) we use some trickery to allow any parameter.

    .. rubric:: On the trickery

    This is all lifted from traitlets, with some supplements to make it more
    flexible. The parser (:class:`argparse.ArgumentParser`) will first try to
    recognize optional arguments using a dictionnary of known arguments and their
    associated :class:`action<argparse.Action>`.
    We use a subclass parser :class:`GreedyArgumentParser` that changes the type of
    that dictionnary just before parsing. We use a custom :class:`DefaultOptionDict`
    that will automatically create an action when asked about an unknown argument.

    The default action is ``nargs="*", type=str``, and for the destination it replaces
    dots in the key by a replacement string (:attr:`_DOT`).

    The function that create the action from the argument name can be changed with
    :meth:`GreedyArgumentParser.set_action_creation` any time after the parser creation.
    """

    parser_class: type[ArgumentParser] = GreedyArgumentParser

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parser = self.create_parser()

    def create_parser(self, **kwargs) -> ArgumentParser:
        """Create a parser instance.

        Can be overwritten if the :attr:`parser_class` attribute is not enough.
        The default action can be here for instance.
        """
        kwargs.setdefault("add_help", False)
        parser = self.parser_class(**kwargs)
        # The default action can be changed here if needed
        # parser.set_action_creation(func)
        return parser

    def get_config(self, *args, **kwargs) -> dict[str, ConfigValue]:
        """Load and return a proper configuration dict.

        This overwrites the common method to parse all values. Since the config has
        been resolved, each config value should be associated to a trait, allowing
        parsing.
        """
        self.config = super().get_config(*args, **kwargs)
        # Parse values using the traits
        for key, val in self.config.items():
            with ConfigErrorHandler(self.app, key):
                val.parse()
        return self.config

    def load_config(self, argv: list[str] | None = None) -> None:
        """Populate the config attribute from CLI.

        Use argparser to obtain key/values.
        Deal with 'help' flags.

        Parameters
        ----------
        argv
            Arguments to parse. If None use the system ones.
        """
        # ArgumentParser does its job
        # We are expecting (action="append", type=str, nargs="*") ie list[list[str]]
        args = vars(self.parser.parse_args(argv))

        # convert to ConfigKey/Value objects
        for name, value in args.items():
            key = name.replace(_DOT, ".")

            if key in self.app.extra_parameters:
                self.app.extra_parameters[key] = value
                continue

            with ConfigErrorHandler(self.app, key):
                # Check that the key was specified only once
                if len(value) > 1:
                    raise MultipleConfigKeyError(key, value)
                value = value[0]
                if len(value) == 1:
                    value = value[0]

                self.add(key, ConfigValue(value, key, origin="CLI"))

        # check if there are any help flags
        if "help" in self.config:
            self.app.help()
            self.app.exit()


# --- File loaders


class FileLoader(ConfigLoader):
    """Load config from a file.

    Common logic goes here.

    Parameters
    ----------
    filename
        Path of configuration file to load.
    """

    extensions: list[str] = []
    """File extensions that are supported by this loader."""

    def __init__(self, app: ApplicationBase, filename: str, *args, **kwargs) -> None:
        super().__init__(app, *args, **kwargs)
        self.filename = filename
        self.full_filename = path.abspath(filename)

    @classmethod
    def can_load(cls, filename: str) -> bool:
        """Return if this loader class is appropriate for this config file.

        This is a classmethod to avoid unnecessary/unwanted library import that might
        happen at initialization.

        By default, only check supported file extensions.
        """
        _, ext = path.splitext(filename)
        return ext.lstrip(".") in cls.extensions

    def to_lines(
        self, comment: t.Any = None, show_existing_keys: bool = False
    ) -> list[str]:
        """Generate lines of a configuration file corresponding to the app config tree.

        If `show_existing_keys` is true, the keys present in the original file are
        loaded into this instance :attr:`config` attribute.

        Parameters
        ----------
        comment
            Include more or less information as comments. Can be one of:

            * full: all information about traits is included
            * no-help: trait help attribute is not included
            * none: no information is included, only the key and default value

            Note that the line containing the key and default value, for instance
            ``traitname = 2`` will be commented since we do not need to parse/load the
            default value.
        show_existing_keys
            If True, do not comment ``key = value`` lines that are present in the
            original file (default is False).
        """
        if show_existing_keys:
            classes = {cls.__name__: cls for cls in self.app._classes_inc_parents()}
            self.get_config(apply_application_traits=False, resolve=False)
            valid = {}
            for key, value in self.config.items():
                keypath = key.split(".")
                if (
                    len(keypath) == 2
                    and keypath[0] in classes
                    and keypath[1] in classes[keypath[0]].class_trait_names(config=True)
                ):
                    for fullkey in self.app.resolve_class_key(keypath):
                        _, scheme, trait = self.app.resolve_key(fullkey)
                        trait._validate(scheme, value.get_value())
                    valid[key] = value
                    continue
                try:
                    fullkey, scheme, trait = self.app.resolve_key(keypath)
                    trait._validate(scheme, value.get_value())
                    valid[key] = value
                except ConfigError:
                    pass
            self.config = valid
        return self._to_lines(comment=comment, show_existing_keys=show_existing_keys)

    def _to_lines(
        self, comment: t.Any = None, show_existing_keys: bool = False
    ) -> list[str]:
        """Generate lines of a configuration file corresponding to the app config tree.

        If `show_existing_keys` is true, the keys present in the original file are
        loaded into this instance :attr:`config` attribute.
        This includes unresolved class-keys. It is advised to pop keys from the
        configuration as the application config-tree is walked. At the end, only
        class keys should be left.

        Parameters
        ----------
        comment
            Include more or less information as comments. Can be one of:

            * full: all information about traits is included
            * no-help: trait help attribute is not included
            * none: no information is included, only the key and default value

            Note that the line containing the key and default value, for instance
            ``traitname = 2`` will be commented since we do not need to parse/load the
            default value.
        show_existing_keys
            If True, do not comment ``key = value`` lines that are present in this
            loader instance :attr:`config` attribute (default is False).
        """
        raise NotImplementedError("Implement for different file formats.")


class TomlkitLoader(FileLoader):
    """Load config from TOML files using tomlkit library.

    The :mod:`tomlkit` library is the default for data-assistant, as it allows precise
    creation of toml files (including comments) which is useful for creating fully
    documented config files.

    Another backend could be used instead. A sibling class would have to be created.

    The library is imported lazily on instanciation, so users that do not use TOML do
    not need to install it.
    """

    extensions = ["toml"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        import tomlkit

        self.backend = tomlkit

    def load_config(self) -> None:
        """Populate the config attribute from TOML file.

        We use :mod:`tomlkit` to parse file.
        """
        with open(self.full_filename) as fp:
            root_table = self.backend.load(fp)

        # flatten tables
        def recurse(table: TOMLContainer, key: list[str]):
            for k, v in table.items():
                newkey = key + [k]
                if isinstance(v, self.backend.api.Table):
                    recurse(v, newkey)
                else:
                    fullkey = ".".join(newkey)
                    value = ConfigValue(v, fullkey, origin=self.filename)
                    # no parsing, directly to values
                    value.value = value.input
                    self.add(fullkey, value)

        recurse(root_table, [])

    def _to_lines(
        self, comment: str = "full", show_existing_keys: bool = False
    ) -> list[str]:
        """Return lines of configuration file corresponding to the app config tree."""
        doc = self.backend.document()

        self.serialize_scheme(
            doc, self.app, [], comment=comment, show_existing_keys=show_existing_keys
        )

        if show_existing_keys:
            class_keys: dict[str, dict[str, t.Any]] = {}
            for key, value in self.config.items():
                cls, name = key.split(".")
                if cls not in class_keys:
                    class_keys[cls] = {}
                class_keys[cls][name] = value.get_value()

            for cls in class_keys:
                tab = self.backend.table()
                for key, value in class_keys[cls].items():
                    tab.add(key, self._sanitize_item(value))
                doc.add(cls, tab)

        return self.backend.dumps(doc).splitlines()

    def serialize_scheme(
        self,
        t: T,
        scheme: Scheme,
        fullpath: list[str],
        comment: str = "full",
        show_existing_keys: bool = False,
    ) -> T:
        """Serialize a Scheme and its subschemes recursively.

        We use the extented capabilities of :mod:`tomlkit`.
        """
        if comment != "none":
            self.wrap_comment(t, scheme.emit_description())

        for name, trait in scheme.traits(config=True).items():
            if comment != "none":
                t.add(self.backend.nl())
            lines: list[str] = []

            fullkey = ".".join(fullpath + [name])
            key_exist = show_existing_keys and fullkey in self.config
            if key_exist:
                value = self.config.pop(fullkey).get_value()
                t.add(name, self._sanitize_item(value))

            # the actual toml code key = value
            # If anything goes wrong we just use str, it may not be valid toml but
            # the user will deal with it.
            try:
                default = self._sanitize_item(trait.default()).as_string()
            except Exception:
                default = str(trait.default())
            if not key_exist:
                lines.append(f"{name} = {default}")

            if comment == "full":
                # a separator between the key = value and block of help/info
                lines.append("-" * len(name))

            if comment != "none":
                fullkey = ".".join(fullpath + [name])
                typehint = get_trait_typehint(trait, "minimal")
                lines.append(f"{fullkey} ({typehint}) default: {default}")

                if isinstance(trait, Enum):
                    lines.append("Accepted values: " + repr(trait.values))

            if comment != "no-help" and trait.help:
                lines += wrap_text(trait.help)

            self.wrap_comment(t, lines)

        for name, subscheme in sorted(scheme.trait_values(subscheme=True).items()):
            t.add(
                name,
                self.serialize_scheme(
                    self.backend.table(),
                    subscheme,
                    fullpath + [name],
                    comment=comment,
                    show_existing_keys=show_existing_keys,
                ),
            )

        return t

    def _sanitize_item(self, value: t.Any) -> Item:
        """Return an Item to use for the line key = value.

        Take care of specific cases when default value is None or a type.
        """
        if value is None:
            return self.backend.items.String.from_raw("")

        # convert types to string
        if isinstance(value, type):
            return self.backend.items.String.from_raw(
                f"{value.__module__}.{value.__name__}"
            )

        return self.backend.item(value)

    def wrap_comment(self, item: Table | TOMLContainer, text: str | list[str]):
        """Wrap text correctly and add it to a toml container as comment lines."""
        if not isinstance(text, str):
            text = "\n".join(text)

        text = dedent(text)
        # remove empty trailing lines
        text = text.rstrip(" \n")
        lines = text.splitlines()

        for line in lines:
            item.add(self.backend.comment(line))


class PyConfigContainer:
    """Object that can define attributes recursively on the fly.

    Allows the config file syntax::

        c.group.subgroup.parameter = 3
        c.another_group.parameter = True

    It patches ``__getattribute__`` to allow this. Any unknown attribute is
    automatically created and assigned a new instance of PyConfigContainer. The
    attributes values can be explored (recursively) in the ``__dict__`` attribute.

    This is a very minimalist approach and caution should be applied if this class is to
    be expanded.
    """

    def __getattribute__(self, key: str) -> t.Any:
        try:
            return super().__getattribute__(key)
        except AttributeError:
            obj = PyConfigContainer()
            self.__setattr__(key, obj)
            return obj


class PyLoader(FileLoader):
    """Load config from a python file.

    Follows the syntax of traitlets python config files::

        c.ClassName.parameter = 1

    but now also::

        c.group.subgroup.parameter = True

    Arbitrary schemes and sub-schemes can be specified. The object ``c`` is already
    defined. It is a simple object only meant to allow for this syntax
    (:class:`PyConfigContainer`). Any code will be run, so some logic can be used in the
    config files directly (changing a value depending on OS or hostname for instance).

    Sub-configs are not supported (but could be if necessary).
    """

    extensions = ["py", "ipy"]

    def load_config(self) -> None:
        """Populate the config attribute from python file.

        Compile the config file, and execute it with the variable ``c`` defined
        as an empty :class:`PyConfigContainer` object.
        """
        read_config = PyConfigContainer()

        # from traitlets.config.loader.PyFileConfigLoader
        namespace = dict(c=read_config, __file__=self.full_filename)
        with open(self.full_filename, "rb") as fp:
            exec(
                compile(source=fp.read(), filename=self.full_filename, mode="exec"),
                namespace,  # globals and locals
                namespace,
            )

        # flatten config
        def recurse(cfg: PyConfigContainer, key: list[str]):
            for k, v in cfg.__dict__.items():
                newkey = key + [k]
                if isinstance(v, PyConfigContainer):
                    recurse(v, newkey)
                else:
                    fullkey = ".".join(newkey)
                    value = ConfigValue(v, fullkey, origin=self.filename)
                    # no parsing, directly to values
                    value.value = value.input
                    self.add(fullkey, value)

        recurse(read_config, [])

    def _to_lines(
        self, comment: str = "full", show_existing_keys: bool = False
    ) -> list[str]:
        """Return lines of configuration file corresponding to the app config tree."""
        lines = self.serialize_scheme(
            self.app, [], comment=comment, show_existing_keys=show_existing_keys
        )

        if show_existing_keys:
            lines.append("")
            for key, value in self.config.items():
                lines.append(f"c.{key} = {value.get_value()!r}")

        # newline at the end of file
        lines.append("")

        return lines

    def serialize_scheme(
        self,
        scheme: Scheme,
        fullpath: list[str],
        comment: str = "full",
        show_existing_keys: bool = False,
    ) -> list[str]:
        """Serialize a Scheme and its subschemes recursively.

        If comments are present, trait are separated by double comment lines (##) that
        can be read by editors as magic cells separations.

        For the key = value lines, we make use of :meth:`TraitType.default_value_repr`.
        """
        lines = []
        if comment != "none":
            lines += self.wrap_comment(scheme.emit_description())

        lines.append("")

        for name, trait in sorted(scheme.traits(config=True).items()):
            try:
                default = trait.default_value_repr()
            except Exception:
                default = repr(trait.default())

            if comment != "none":
                typehint = get_trait_typehint(trait, "minimal")
                lines.append(f"## {name} ({typehint}) default: {default}")

            fullkey = ".".join(fullpath + [name])

            key_exist = show_existing_keys and fullkey in self.config
            if key_exist:
                value = self.config.pop(fullkey).get_value()
                default = repr(value)

            keyval = f"c.{fullkey} = {default}"
            if not key_exist:
                keyval = "# " + keyval
            lines.append(keyval)

            if comment != "none" and isinstance(trait, Enum):
                lines.append("# Accepted values: " + repr(trait.values))

            if comment != "no-help" and trait.help:
                lines += self.wrap_comment(trait.help)

            self.wrap_comment(lines)
            if comment != "none":
                lines.append("")

        for name, subscheme in sorted(scheme.trait_values(subscheme=True).items()):
            lines.append("")
            lines.append(f"## {subscheme.__class__.__name__} (.{name}) ##")
            underline(lines, "#")
            lines += self.serialize_scheme(
                subscheme,
                fullpath + [name],
                comment=comment,
                show_existing_keys=show_existing_keys,
            )

        return lines

    def wrap_comment(self, text: str | list[str]) -> list[str]:
        """Wrap text and return it as commented lines."""
        if not isinstance(text, str):
            text = "\n".join(text)

        text = dedent(text)
        # remove empty trailing lines
        text = text.rstrip(" \n")
        lines = wrap_text(text)
        lines = [f"# {line}" for line in lines]

        lines = [line.rstrip() for line in lines]

        return lines


class DictLikeLoaderMixin(ConfigLoader):
    """Load a configuration from a mapping.

    As there are no way to differentiate between a mapping for a dictionary trait and
    one for a nested scheme, we need to check the existing keys before resolving. We
    only look for existing subschemes and aliases, otherwise we assume this is a
    dict-like value.
    """

    def resolve_mapping(self, input: abc.Mapping, origin: str | None = None):
        """Flatten an input nested mapping."""
        # Some keys might be dot-separated. To make sure we are completely nested:
        input = flatten_dict(input)
        input = nest_dict(input)

        def recurse(d: abc.Mapping, scheme: type[Scheme], key: list[str]):
            for k, v in d.items():
                if k in scheme._subschemes:
                    assert isinstance(v, abc.Mapping)
                    recurse(v, scheme._subschemes[k], key + [k])
                elif k in scheme.aliases:
                    assert isinstance(v, abc.Mapping)
                    # resolve alias
                    sub = scheme
                    alias = scheme.aliases[k].split(".")
                    for al in alias:
                        sub = sub._subschemes[al]
                    recurse(v, sub, key + alias)
                else:
                    fullkey = ".".join(key + [k])
                    value = ConfigValue(v, fullkey, origin=origin)
                    # no parsing, directly to values
                    value.value = value.input
                    self.add(fullkey, value)

        recurse(input, self.app.__class__, [])


class DictLikeLoader(DictLikeLoaderMixin):
    """Loader for mappings."""

    def load_config(self, input: abc.Mapping) -> None:
        """Populate the config attribute from a nested mapping."""
        self.config = self.resolve_mapping(input)


class YamlLoader(DictLikeLoaderMixin, FileLoader):
    """Loader for Yaml files.

    Not implemented yet.
    """

    extensions = ["yaml", "yml"]

    def load_config(self) -> None:
        raise NotImplementedError()


class JsonEncoderTypes(json.JSONEncoder):
    def default(self, o: t.Any) -> t.Any:
        if isinstance(o, type):
            mod = o.__module__
            name = o.__name__
            return f"{mod}.{name}"
        return super().default(o)


class JsonLoader(DictLikeLoaderMixin, FileLoader):
    """Loader for JSON files.

    :Experimental:
    """

    extensions = ["json"]

    JSON_DECODER: type[json.JSONDecoder] | None = None
    """Custom json decoder to use."""
    JSON_ENCODER: type[json.JSONEncoder] | None = JsonEncoderTypes
    """Custom json encoder to use."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.app.log.warning("%s loader is experimental.", self.__class__)
        import json

        self.backend = json

    def load_config(self) -> None:
        """Populate the config attribute from TOML file.

        We use builtin :mod:`json` to parse file, with eventually a custom decoder
        specified by :attr:`JSON_DECODER`.
        """
        with open(self.full_filename) as fp:
            input = json.load(fp, cls=self.JSON_DECODER)

        self.resolve_mapping(input, origin=self.filename)

    def _to_lines(
        self, comment: str = "full", show_existing_keys: bool = False
    ) -> list[str]:
        """Serialize configuration."""
        if comment != "none":
            self.app.log.warning("No comments possible in JSON format.")

        output = self.app.values_recursive()
        # TODO Merge with self.config
        # TODO Options: maybe only show values differing from default?
        dump = json.dumps(output, cls=self.JSON_ENCODER, indent=2)

        return dump.splitlines()
