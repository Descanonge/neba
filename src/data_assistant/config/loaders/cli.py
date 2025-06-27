"""Loading configuration from command line arguments."""

import argparse
import sys
import typing as t
from collections import abc

from traitlets import TraitType

try:
    import argcomplete

    _HAS_ARGCOMPLETE = True
except ImportError:
    _HAS_ARGCOMPLETE = False

from data_assistant.config.util import (
    MultipleConfigKeyError,
    UnknownConfigKeyError,
    get_trait_typehint,
)

from .core import ConfigLoader, ConfigValue, Undefined

_DOT = "__DOT__"
"""String replacement for dots in command line keys."""


class CLIConfigValue(ConfigValue):
    def __init__(self, input: t.Any, key: str, origin: str | None = "CLI"):
        super().__init__(input, key, origin=origin)

    def get_value(self) -> t.Any:
        if self.value is not Undefined:
            return self.value

        self.parse()
        return self.value


class CLILoader(ConfigLoader):
    """Load config from command line.

    This uses the standard module :mod:`argparse`. The default action is ``nargs="*",
    type=str``, and for the destination it replaces dots in the key by a replacement
    string (:attr:`_DOT`).
    """

    allow_kebab: bool = True
    """Whether to propose parameters under both snake case `my_parameter`
    and kebab case `my-parameter`."""

    prefix: str = "both"
    """How much hyphens to use as prefix, either 'one', 'two', or 'both'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parser = self.create_parser()

        self.parser.add_argument("-h", "--help", action="store_true")
        self.parser.add_argument("--list-parameters", action="store_true")

        self.traits = self.app.traits_recursive(aliases=True)
        for orphan in self.app._imported_orphans.values():
            for key, trait in orphan.traits_recursive(aliases=True).items():
                self.traits[f"{orphan.__name__}.{key}"] = trait

        for key, trait in self.traits.items():
            self.add_argument(key, trait)

        if _HAS_ARGCOMPLETE:
            argcomplete.autocomplete(self.parser)

    def create_parser(self, **kwargs) -> argparse.ArgumentParser:
        """Create a parser instance."""
        parser = argparse.ArgumentParser(
            add_help=False,
            argument_default=argparse.SUPPRESS,
            exit_on_error=False,
            allow_abbrev=False,
            **kwargs,
        )
        return parser

    def add_argument(self, key: str, trait: TraitType):
        """Add argument to the parser."""
        keys = [key]
        if self.allow_kebab:
            keys.append(key.replace("_", "-"))

        flags = []
        if self.prefix in ["one", "both"]:
            flags += [f"-{k}" for k in keys]
        if self.prefix in ["two", "both"]:
            flags += [f"--{k}" for k in keys]

        self.parser.add_argument(
            *flags,
            action="append",
            dest=key.replace(".", _DOT),
            type=str,
            nargs="*",
            metavar="",
            help=trait.help.split("\n")[0].strip(),
        )

    def load_config(self, argv: list[str] | None = None) -> abc.Iterator[ConfigValue]:
        """Populate the config attribute from CLI.

        Use argparser to obtain key/values. Deal with 'help' flags.

        Parameters
        ----------
        argv
            Arguments to parse. If None use the system ones.
        """
        # ArgumentParser does its job
        # We are expecting (action="append", type=str, nargs="*") ie list[list[str]]
        args, extra = self.parser.parse_known_args(argv)
        if extra:
            raise UnknownConfigKeyError(
                f"Unrecognized argument(s): {', '.join(extra)}, "
                "use -h/--help or --list_parameters to see available3"
            )

        dargs = vars(args)
        if "help" in dargs:
            dargs.pop("help")
            self.app.help()
            self.app.exit()

        if "list_parameters" in dargs:
            hyphens = "-" if self.prefix == "one" else "--"
            lines = [
                f"{hyphens}{k} ({get_trait_typehint(v, 'minimal')})"
                for k, v in self.traits.items()
            ]
            print("\n".join(lines), file=sys.stderr)
            self.app.exit()

        # convert to ConfigKey/Value objects
        for name, value in dargs.items():
            key = name.replace(_DOT, ".")

            # Check that the key was specified only once
            if len(value) > 1:
                raise MultipleConfigKeyError(key, value)
            value = value[0]
            if len(value) == 1:
                value = value[0]

            yield CLIConfigValue(value, key)
