"""Configuration loaders.

Extend loaders defined by traitlets for our needs (mainly nested configuration).
"""
from __future__ import annotations

import argparse
import logging
import re
from argparse import Action, ArgumentParser, _StoreAction
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from .scheme import Scheme

if TYPE_CHECKING:
    from .application import ApplicationBase

from traitlets.traitlets import TraitType

_DOT = "__DOT__"

ConfigValueType = str | list[str]


class ConfigKV:
    def __init__(self, key: str, input: ConfigValueType, origin: str | None = None):
        if isinstance(input, list):
            if len(input) == 1:
                input = input[0]

        self.key = key
        self.key_init = key
        self.input = input
        self.value: Any | None = None
        self.trait: TraitType | None = None
        self.origin = origin

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

    @property
    def path(self) -> list[str]:
        return self.key.split(".")

    @property
    def prefix(self) -> str:
        return self.path[0]

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


NestedKVType = dict[str, ConfigKV | dict[str, "NestedKVType"]]


class ConfigLoader:
    def __init__(self, app: ApplicationBase, log: logging.Logger | None = None):
        self.app = app
        if log is None:
            log = logging.getLogger(__name__)
        self.log = log
        self.config: NestedKVType = {}

    def clear(self) -> None:
        self.config.clear()

    def load_config(self) -> NestedKVType:
        raise NotImplementedError

    def normalize_keys(self, config: Sequence[ConfigKV]) -> NestedKVType:
        """Normalize keys path and parse its value."""
        class_keys: dict[str, ConfigKV] = {}
        keys: list[ConfigKV] = []

        classes_by_name = {cls.__name__: cls for cls in self.app.classes}

        for key in config:
            # Place class keys appart
            if (cls := classes_by_name.get(key.prefix, None)) is not None:
                if len(key.path) > 2:
                    raise KeyError(
                        f"A parameter --Class.trait cannot be nested ({key.key_init})."
                    )
                key.trait = cls.class_traits()[key.path[1]]
                key.parse()
                class_keys[key.prefix] = key
                continue
            keys.append(key)

        # Generate output skeleton, and fill --Class.trait parameters
        def recurse(scheme: type[Scheme]) -> NestedKVType:
            out: NestedKVType = {}
            for name, subscheme in scheme._subschemes.items():
                out[name] = recurse(subscheme)  # type: ignore[assignment]
            if (key := class_keys.get(scheme.__name__, None)) is not None:
                out[key.path[1]] = key
            return out

        output = recurse(self.app.__class__)

        outsec = output
        for key in keys:
            scheme: type[Scheme] = self.app.__class__
            for subkey in key.path:
                # TODO: Aliases/shortcuts
                if subkey in scheme._subschemes:
                    scheme = scheme._subschemes[subkey]
                elif (
                    trait := scheme.class_own_traits(config=True).get(subkey, None)
                ) is not None:
                    key.trait = trait
                    key.parse()
                    outsec[subkey] = key
                else:
                    raise KeyError(f"Key '{key.key_init}' not found in specification.")

        return output


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

    def load_config(self, argv=None, raiseerror: bool = True) -> NestedKVType:
        self.clear()
        config = vars(self.parser.parse_args())
        keyvals = [
            ConfigKV(name.replace(_DOT, "."), value, origin="CLI")
            for name, value in config.items()
        ]
        self.config = self.normalize_keys(keyvals)
        return self.config


# --- File loaders


class FileLoader(ConfigLoader):
    extensions: list[str]

    def __init__(self, filepath: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.filepath = filepath


class TomlLoader(FileLoader):
    extensions = ["toml"]


class YamlLoader(FileLoader):
    extensions = ["yaml", "yml"]


class PyLoader(FileLoader):
    extensions = ["py", "ipy"]
