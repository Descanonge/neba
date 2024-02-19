"""Configuration loaders.

Extend loaders defined by traitlets for our needs (mainly nested configuration).
"""
from __future__ import annotations

import argparse
import importlib
import logging
import re
import sys
from argparse import Action, ArgumentParser, _StoreAction
from collections.abc import Sequence, Callable
from typing import TYPE_CHECKING, Any
from traitlets.traitlets import HasTraits
from traitlets.utils.sentinel import Sentinel

if TYPE_CHECKING:
    from .application import ApplicationBase

from traitlets.traitlets import TraitType

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

    def get_config(self) -> dict[str, ConfigValue]:
        raise NotImplementedError


class _DefaultOptionDict(dict[str, Action]):
    option_pattern = re.compile(r"^--?[A-Za-z_]\w*(\.\w+)*$")

    def _add_action(self, key: str) -> None:
        self[key] = self._create_action(key)

    @staticmethod
    def _create_action(key: str) -> Action:
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

    # TODO use a catch error decorator
    def get_config(self, argv: list[str] | None = None) -> dict[str, ConfigValue]:
        self.clear()

        # ArgumentParser does its job
        args = vars(self.parser.parse_args(argv))

        # convert to ConfigKey/Value objects
        config = {}
        for name, value in args.items():
            key = name.replace(_DOT, ".")
            config[key] = ConfigValue(value, key, origin="CLI")

        # check if there are any help flags
        if "help" in config:
            print("\n".join(self.app.emit_help()))
            self.app.exit()

        # resolve paths
        config = self.app.resolve_config(config)
        # Parse using the traits
        for val in config.values():
            val.parse()
        self.config = config
        return self.config


# --- File loaders


class FileLoader(ConfigLoader):
    extensions: list[str]

    def __init__(self, filepath: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.filepath = filepath


class TomlKitLoader(FileLoader):
    extensions = ["toml"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        import tomlkit

        self.backend = tomlkit

    # TODO use a catch error decorator
    # so that any error is raise as a ConfigLoadingError, easy to catch in App
    def get_config(self, filepath: str | None = None) -> dict[str, ConfigValue]:
        # TODO Check file exist ?
        if filepath is None:
            filepath = self.filepath
        self.clear()
        with open(filepath) as fp:
            root_table = self.backend.load(fp)

        # flatten the dict
        config = {}

        def recurse(table, key):
            for k, v in table.items():
                newkey = key + [k]
                if isinstance(v, self.backend.api.Table):
                    recurse(v, newkey)
                else:
                    fullkey = ".".join(newkey)
                    value = ConfigValue(v.unwrap(), fullkey, origin=filepath)
                    # no parsing, directly to values
                    value.value = value.input
                    config[fullkey] = value

        recurse(root_table, [])

        config = self.app.resolve_config(config)
        self.config = config
        return self.config


class YamlLoader(FileLoader):
    extensions = ["yaml", "yml"]


class PyLoader(FileLoader):
    extensions = ["py", "ipy"]
