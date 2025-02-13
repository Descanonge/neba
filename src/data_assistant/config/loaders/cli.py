"""Loading configuration from command line arguments."""

import argparse
import re
import typing as t
from argparse import Action, ArgumentParser, _AppendAction
from collections import abc

from ..util import ConfigErrorHandler, MultipleConfigKeyError
from .core import ConfigLoader, ConfigValue, Undefined

_DOT = "__DOT__"
"""String replacement for dots in command line keys."""


class DefaultOptionDict(dict[str, Action]):
    """Dictionnary that create missing actions on the fly.

    Meant to replace :attr:`argparse.ArgumentParser._option_string_actions`. Any
    argument not already recognized, and that match the regular expression
    :attr:`option_pattern`, will automatically be assigned an action on the fly by
    :meth:`_create_action` (this static method can be replaced using
    :meth:`_set_action_create`).
    """

    option_pattern = re.compile(r"^--?[A-Za-z_][\w-]*(\.[\w-]+)*$")
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

    def load_config(self, argv: list[str] | None = None) -> abc.Iterator[ConfigValue]:
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

            if key == "help":
                self.app.help()
                self.app.exit()

            if key in self.app.extra_parameters:
                self.app.extra_parameters[key] = value
                continue

            # Check that the key was specified only once
            if len(value) > 1:
                raise MultipleConfigKeyError(key, value)
            value = value[0]
            if len(value) == 1:
                value = value[0]

            yield CLIConfigValue(value, key)
