"""Configuration loaders.

Extend loaders defined by traitlets for our needs (mainly nested configuration).
"""
from __future__ import annotations

import argparse
import importlib
import logging
import re
from argparse import Action, ArgumentParser, _StoreAction
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any
from traitlets.traitlets import HasTraits

if TYPE_CHECKING:
    from .application import ApplicationBase

from traitlets.traitlets import TraitType

_DOT = "__DOT__"


class ConfigKV:
    def __init__(self, key: str, input: Any, origin: str | None = None):
        if isinstance(input, list):
            if len(input) == 1:
                input = input[0]

        self.key = key
        self.key_init = key
        self.input = input
        self.origin = origin

        self.value: Any | None = None
        self.trait: TraitType | None = None
        self.container_cls: type[HasTraits] | None = None
        self.priority: int = 0

    def __str__(self) -> str:
        s = [f"{self.key_init}:"]
        if self.value is not None:
            s.append(str(self.value))
        else:
            s.append(str(self.input))
        if self.origin is not None:
            s.append(f"({self.origin})")
        return " ".join(s)

    def __repr__(self) -> str:
        return "\n".join([super().__repr__(), str(self)])

    def copy(self, **kwargs) -> ConfigKV:
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

        out = self.__class__(key=self.key_init, input=self.input)
        for attr, value in data.items():
            setattr(out, attr, value)
        return out

    @property
    def path(self) -> list[str]:
        return self.key.split(".")

    @property
    def prefix(self) -> str:
        return self.path[0]

    @property
    def lastname(self) -> str:
        return self.path[-1]

    def parse(self) -> None:
        if self.trait is None:
            raise RuntimeError(f"Cannot parse key {self.key_init}, has not trait.")
        if isinstance(self.input, str):
            self.value = self.trait.from_string(self.input)
            return
        try:
            self.value = self.trait.from_string_list(self.input)  # type: ignore
        except AttributeError as err:
            raise AttributeError(
                f"Expecting Trait {self.trait.__class__} "
                f"for key {self.key_init} to be able to parse lists with "
                "`from_string_list()`."
            ) from err

    # def apply(self) -> None:
    #     if self.container is None:
    #         raise RuntimeError(f"No container for key '{self.key_init}'")
    #     setattr(self.container, self.lastname, self.value)


def to_value_dict(config: dict[str, ConfigKV]) -> dict[str, Any]:
    output = {key: kv.value for key, kv in config.items()}
    return output


def to_nested_dict(config: dict[str, ConfigKV]) -> dict:
    nested_conf: dict[str, Any] = {}
    for kv in config.values():
        subconf = nested_conf
        for subkey in kv.path[:-1]:
            subconf = subconf.setdefault(subkey, {})
        subconf[kv.lastname] = kv
    return nested_conf


class ConfigLoader:
    def __init__(self, app: ApplicationBase, log: logging.Logger | None = None):
        self.app = app
        if log is None:
            log = logging.getLogger(__name__)
        self.log = log
        self.config: dict[str, ConfigKV] = {}

    def clear(self) -> None:
        self.config.clear()

    def get_config(self) -> dict[str, ConfigKV]:
        raise NotImplementedError


class _GreedyDefaultOptionDict(dict[str, Action]):
    option_pattern = re.compile(r"^--?[A-Za-z_]\w*(\.\w+)*$")

    def _add_action(self, key: str) -> None:
        self[key] = _StoreAction(
            option_strings=[key],
            dest=key.lstrip("-").replace(".", _DOT),
            nargs="+",
        )

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

    defaultdict_class: type[dict] = _GreedyDefaultOptionDict

    def parse_known_args(  # type:ignore[override]
        self,
        args: Sequence[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> tuple[argparse.Namespace | None, list[str]]:
        # must be done immediately prior to parsing because if we do it in init,
        # registration of explicit actions via parser.add_option will fail during setup
        for container in (self, self._optionals):
            container._option_string_actions = self.defaultdict_class(
                container._option_string_actions
            )
        return super().parse_known_args(args, namespace)


class CLILoader(ConfigLoader):
    parser_class: type[ArgumentParser] = GreedyArgumentParser

    def __init__(self, app: ApplicationBase, **kwargs):
        super().__init__(app, **kwargs)
        self.parser: ArgumentParser = self.create_parser()

    def create_parser(self, **kwargs) -> ArgumentParser:
        return self.parser_class(**kwargs)

    # TODO use a catch error decorator
    def get_config(self, argv=None) -> dict[str, ConfigKV]:
        # if argv is None ?
        self.clear()
        args = vars(self.parser.parse_args(argv))
        # convert to ConfigKV objects
        keyvals = [
            ConfigKV(name.replace(_DOT, "."), value, origin="CLI")
            for name, value in args.items()
        ]
        config = {kv.key: kv for kv in keyvals}
        # resolve paths
        config = self.app.resolve_config(config)
        # Parse using the traits
        for kv in config.values():
            kv.parse()
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
    def get_config(self, filepath: str | None = None) -> dict[str, ConfigKV]:
        # TODO Check file exist ?
        if filepath is None:
            filepath = self.filepath
        self.clear()
        with open(filepath) as fp:
            root_table = self.backend.load(fp)

        # flatten the dict
        keyvals = []

        def recurse(table, key):
            for k, v in table.items():
                newkey = key + [k]
                if isinstance(v, self.backend.api.Table):
                    recurse(v, newkey)
                else:
                    keyvals.append(ConfigKV(".".join(newkey), v.unwrap()))

        recurse(root_table, [])

        # no parsing, directly to values
        for kv in keyvals:
            kv.value = kv.input

        config = {kv.key: kv for kv in keyvals}
        config = self.app.resolve_config(config)
        self.config = config
        return self.config


class YamlLoader(FileLoader):
    extensions = ["yaml", "yml"]


class PyLoader(FileLoader):
    extensions = ["py", "ipy"]
