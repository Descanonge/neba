"""Configuration loaders.

Extend loaders defined by traitlets for our needs (mainly nested configuration).
"""
from __future__ import annotations

import argparse
import logging
import re
from argparse import Action, ArgumentParser, _StoreAction
from collections.abc import Callable, Sequence
from os import path
from textwrap import dedent
from typing import TYPE_CHECKING, Any, overload

from traitlets.traitlets import HasTraits, TraitType, Enum
from traitlets.utils.sentinel import Sentinel

from .util import get_trait_typehint, wrap_text


if TYPE_CHECKING:
    from tomlkit.container import Container, Table
    from tomlkit.toml_document import TOMLDocument

    from .application import ApplicationBase
    from .scheme import Scheme

_DOT = "__DOT__"


Undefined = Sentinel(
    "Undefined", "data-assistant", "Configuration value not (yet) set or parsed."
)


class ConfigValue:
    def __init__(self, input: Any, key: str, origin: str | None = None):
        if isinstance(input, list):
            if len(input) == 1:
                input = input[0]

        self.key = key
        self.input = input
        self.origin = origin

        self.value: Any = Undefined
        self.trait: TraitType | None = None
        self.container_cls: type[HasTraits] | None = None
        self.priority: int = 0

    def __str__(self) -> str:
        s = [str(self.get_value())]
        if self.origin is not None:
            s.append(f"({self.origin})")
        return " ".join(s)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)})"

    def copy(self, **kwargs) -> ConfigValue:
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

    def get_value(self) -> Any:
        if self.value is not Undefined:
            return self.value
        return self.input

    def parse(self) -> None:
        if self.trait is None:
            raise RuntimeError(f"Cannot parse key {self.key}, has not trait.")
        if isinstance(self.input, str):
            self.value = self.trait.from_string(self.input)
            return
        try:
            self.value = self.trait.from_string_list(self.input)  # type: ignore
        except AttributeError as err:
            raise AttributeError(
                f"Expecting Trait {self.trait.__class__} "
                f"for key {self.key} to be able to parse lists with "
                "`from_string_list()`."
            ) from err

    # def apply(self) -> None:
    #     if self.container is None:
    #         raise RuntimeError(f"No container for key '{self.key_init}'")
    #     setattr(self.container, self.lastname, self.value)


def to_dict(config: dict[str, ConfigValue]) -> dict[str, Any]:
    output = {str(key): val.get_value() for key, val in config.items()}
    return output


def to_nested_dict(config: dict[str, ConfigValue]) -> dict[str, Any]:
    nested_conf: dict[str, Any] = {}
    for key, val in config.items():
        subconf = nested_conf
        for subkey in key.split(".")[:-1]:
            subconf = subconf.setdefault(subkey, {})
        subconf[key.split(".")[-1]] = val
    return nested_conf


class ConfigLoader:
    def __init__(self, app: ApplicationBase, log: logging.Logger | None = None):
        self.app = app
        if log is None:
            log = logging.getLogger(__name__)
        self.log = log
        self.config: dict[str, ConfigValue] = {}

    def clear(self) -> None:
        self.config.clear()

    def get_config(self, *args, **kwargs) -> dict[str, ConfigValue]:
        self.clear()
        self.config = self.load_config(*args, **kwargs)
        return self.app.resolve_config(self.config)

    def load_config(self) -> dict[str, ConfigValue]:
        raise NotImplementedError


class _DefaultOptionDict(dict[str, Action]):
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

        Default action is "store", of type ``str``, with ``nargs=*`` (any number of
        arguments). The destination is the argument name, stripped of leading hyphens,
        and with dots "." replaced by :any:`_DOT` (``__DOT__``).
        """
        action = _StoreAction(
            option_strings=[key],
            dest=key.lstrip("-").replace(".", _DOT),
            type=str,
            nargs="*",
        )
        return action

    @classmethod
    def _set_action_creation(cls, func: Callable[[str], Action]) -> None:
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

    def get(self, key, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class GreedyArgumentParser(ArgumentParser):
    """Subclass of ArgumentParser that accepts any option."""

    _action_creation_func: Callable[[str], Action] | None = None

    def set_action_creation(self, func: Callable[[str], Action]) -> None:
        """Change the default action creation function.

        By using :class:`_DefaultOptionDict` unknown arguments will create actions on
        the fly. Replace the default function by ``func``, which must be an unbound
        method or simple function that takes the argument and return an action.
        """
        self._action_creation_func = func

    def parse_known_args(  # type:ignore[override]
        self,
        args: Sequence[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> tuple[argparse.Namespace | None, list[str]]:
        # must be done immediately prior to parsing because if we do it in init,
        # registration of explicit actions via parser.add_option will fail during setup

        # Setup defaultdict
        defaultdict_class = _DefaultOptionDict
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
    each and every possible argument we use some trickery to allow any parameter.
    Any parameter received can be of the form:
    * SchemeClassName.parameter
    * group.subgroup.parameter (with as much nesting as needed)
    * alias.parameter
    followed by one or more arguments.

    Each parameter will be associated to its corresponding trait and parsed (using the
    trait). Parameters that do not conform to the specified schemes and traits will
    raise exceptions.

    .. rubric:: On the trickery

    To allow for any parameter to be accepter by the parser, we have to do some
    trickery. This is all lifted from traitlets, with some supplements to make it more
    flexible. The parser (:class:`argparse.ArgumentParser`) will find first try to
    recognize optional arguments using a dictionnary.
    We use a subclass :class:`GreedyArgumentParser` that change the class of that
    dictionnary just before parsing. We use a custom :class:`_DefaultOptionDict` that
    will automatically create an action when asked about an unknown argument.

    The function that create the action from the argument name can be changed with
    :meth:`GreedyArgumentParser.set_action_creation` any time after the parser creation.
    """

    parser_class: type[ArgumentParser] = GreedyArgumentParser

    def __init__(self, app: ApplicationBase, **kwargs):
        super().__init__(app, **kwargs)
        self.parser = self.create_parser()

    def create_parser(self, **kwargs) -> ArgumentParser:
        kwargs.setdefault("add_help", False)
        parser = self.parser_class(**kwargs)
        # The default action can be changed here if needed
        # parser.set_action_creation(func)
        return parser

    def get_config(self, argv: list[str] | None = None) -> dict[str, ConfigValue]:
        self.config = super().get_config(argv)
        # Parse values using the traits
        for val in self.config.values():
            val.parse()
        return self.config

    # TODO use a catch error decorator
    def load_config(self, argv: list[str] | None = None) -> dict[str, ConfigValue]:
        # ArgumentParser does its job
        args = vars(self.parser.parse_args(argv))

        # convert to ConfigKey/Value objects
        config = {}
        for name, value in args.items():
            key = name.replace(_DOT, ".")
            config[key] = ConfigValue(value, key, origin="CLI")

        # check if there are any help flags
        if "help" in config:
            self.app.help()
            self.app.exit()

        return config


# --- File loaders


class FileLoader(ConfigLoader):
    """Load config from a file.

    Common logic goes here.
    """

    extensions: list[str] = []

    def __init__(self, filename: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.filename = filename
        self.full_filename = path.abspath(filename)

    @classmethod
    def can_load(cls, filename: str) -> bool:
        """Return if this loader class appropriate for this config file.

        This is a classmethod to avoid unnecessary/unwanted library import that might
        happen at initialization.
        """
        _, ext = path.splitext(filename)
        return ext.lstrip(".") in cls.extensions

    def write(self) -> None:
        raise NotImplementedError()

    def to_lines(self, comment: Any = None) -> list[str]:
        """Return lines of configuration file corresponding to the app config tree.

        Parameters
        ----------
        comment
            Include more or less information in comments. Can be one of:
            * full: all information about traits is included
            * no-help: help string is not included
            * none: no information is included, only the key and default value
            Note that the line containing the key and default value, for instance
            ``traitname = 2`` will be commented since we do not need to parse/load the
            default value.
        """
        raise NotImplementedError("Implement for different file formats.")


class TomlKitLoader(FileLoader):
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

    # TODO use a catch error decorator
    # so that any error is raise as a ConfigLoadingError, easy to catch in App
    def load_config(self) -> dict[str, ConfigValue]:
        with open(self.full_filename) as fp:
            root_table = self.backend.load(fp)

        # flatten tables
        def recurse(table: Container, key: list[str]):
            for k, v in table.items():
                newkey = key + [k]
                if isinstance(v, self.backend.api.Table):
                    recurse(v, newkey)
                else:
                    fullkey = ".".join(newkey)
                    value = ConfigValue(v, fullkey, origin=self.filename)
                    # no parsing, directly to values
                    value.value = value.input
                    self.config[fullkey] = value

        recurse(root_table, [])
        return self.config

    def to_lines(self, comment: str = "full") -> list[str]:
        """Return lines of configuration file corresponding to the app config tree.

        Parameters
        ----------
        comment
            Include more or less information in comments. Can be one of:
            * full: all information about traits is included
            * no-help: help string is not included
            * none: no information is included, only the key and default value
            Note that the line containing the key and default value, for instance
            ``traitname = 2`` will be commented since we do not need to parse/load the
            default value.
        """
        doc = self.backend.document()

        self.serialize_scheme(self.app, [], comment, doc)

        return self.backend.dumps(doc).splitlines()

    @overload
    def serialize_scheme(
        self,
        scheme: ApplicationBase,
        fullpath: list[str],
        comment: str,
        container: TOMLDocument,
    ) -> TOMLDocument:
        ...

    @overload
    def serialize_scheme(
        self,
        scheme: Scheme,
        fullpath: list[str],
        comment: str,
        container: None = None,
    ) -> Table:
        ...

    def serialize_scheme(
        self,
        scheme: Scheme,
        fullpath: list[str],
        comment: str,
        container: TOMLDocument | None = None,
    ) -> Table | TOMLDocument:
        t: Container | Table
        if container is None:
            t = self.backend.table()
        else:
            t = container

        if comment != "none":
            self.wrap_comment(t, scheme.emit_description())
            t.add(self.backend.nl())

        for name, trait in sorted(scheme.traits(config=True).items()):
            lines: list[str] = []
            # the actual toml code key = value
            # If anything goes wrong we just use str, it may not be valid toml but
            # the user will deal with it.
            try:
                value = self.get_trait_keyval(trait)
            except Exception:
                value = str(value)
            lines.append(f"{name} = {value}")

            if comment == "full":
                # a separator between the key = value and block of help/info
                lines.append("-" * len(name))

            if comment != "none":
                fullkey = ".".join(fullpath + [name])
                typehint = get_trait_typehint(trait, "minimal")
                lines.append(f"{fullkey} ({typehint})")

                if isinstance(trait, Enum):
                    lines.append("Accepted values: " + repr(trait.values))

            if comment != "no-help" and trait.help:
                lines += wrap_text(trait.help)

            self.wrap_comment(t, lines)
            if comment != "none":
                t.add(self.backend.nl())

        for name, subscheme in sorted(scheme.trait_values(subscheme=True).items()):
            t.add(self.backend.nl())
            t.add(name, self.serialize_scheme(subscheme, fullpath + [name], comment))

        return t

    def get_trait_keyval(self, trait: TraitType) -> str:
        # The actual toml code key = value.
        value = trait.default()

        if value is None:
            return ""

        # convert types to string
        if isinstance(value, type):
            return f'"{value.__module__}.{value.__name__}"'

        item = self.backend.item(value)
        return item.as_string()

    def wrap_comment(self, item: Table | Container, text: str | list[str]):
        if not isinstance(text, str):
            text = "\n".join(text)

        text = dedent(text)
        # remove empty trailing lines
        text = text.rstrip(" \n")
        lines = text.splitlines()

        for line in lines:
            item.add(self.backend.comment(line))


class YamlLoader(FileLoader):
    extensions = ["yaml", "yml"]


class _ReadConfig:
    """Object that can define attributes recursively on the fly.

    Allows the config file syntax:

        c.group.subgroup.parameter = 3
        c.another_group.parameter = True

    It patches ``__getattribute__`` to allow this. Any unknown attribute is
    automatically created and assigned a new instance of _ReadConfig. The attributes
    values can be explored (recursively) in the ``__dict__`` attribute.

    This is a very minimalist approach and caution should be applied if this class is to
    be expanded.
    """

    def __getattribute__(self, key: str) -> Any:
        try:
            return super().__getattribute__(key)
        except AttributeError:
            obj = _ReadConfig()
            self.__setattr__(key, obj)
            return obj


class PyLoader(FileLoader):
    """Load config from a python file.

    Follows the syntax of traitlets python config files:

        c.ClassName.parameter = 1

    but now also:

        c.group.subgroup.parameter = True

    Arbitrary schemes and sub-schemes can be specified. The object ``c`` is already
    defined. It is a simple object only meant to allow for this syntax
    (:class:`_ReadConfig`). Any code will be run, so some logic can be used in the
    config files directly (changing a value depending on OS or hostname for instance).

    Sub-configs are not supported (but could be if necessary).
    """

    extensions = ["py", "ipy"]

    def load_config(self) -> dict[str, ConfigValue]:
        read_config = _ReadConfig()

        # from traitlets.config.loader.PyFileConfigLoader
        namespace = dict(c=read_config, __file__=self.full_filename)
        with open(self.full_filename, "rb") as fp:
            exec(
                compile(source=fp.read(), filename=self.full_filename, mode="exec"),
                namespace,  # globals and locals
                namespace,
            )

        # flatten config
        def recurse(cfg: _ReadConfig, key: list[str]):
            for k, v in cfg.__dict__.items():
                newkey = key + [k]
                if isinstance(v, _ReadConfig):
                    recurse(v, newkey)
                else:
                    fullkey = ".".join(newkey)
                    value = ConfigValue(v, fullkey, origin=self.filename)
                    # no parsing, directly to values
                    value.value = value.input
                    self.config[fullkey] = value

        recurse(read_config, [])
        return self.config
