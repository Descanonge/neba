"""Project-wide parameters management."""

import argparse
import os
from collections.abc import Sequence
from os import path
from typing import Any, Callable

import configargparse  # type: ignore

PathLike = str | os.PathLike


class ParametersManager:
    """Retrieve parameters from command line and config files.

    Allows to automatically construct an :class:`configargparse.ArgumentParser`
    from a list of previously registered arguments (or parameters).
    Useful for project-wide definition of parameters that are not necessarily
    used by all scripts. Each script can retrieve a subset of parameters.

    .. note::

        This class uses :class:`configargparse.ArgumentParser` but this is
        interchangeable with built-in :class:`argparse.ArgumentParser`.
        Only :func:`new_parser` needs to be overriden to change the parser class.
    """

    DEFAULT_CONFIG_FILES: list[PathLike] = ['./parameters.ini']

    def __init__(self) -> None:
        self.parameters_args: dict[str, tuple[tuple[Any], dict]] = {}
        self._actions: dict[str, argparse.Action] = {}
        self.parser = self.new_parser()

    def register_parameter(self, *args, **kwargs):
        """Register a new parameter definition.

        Arguments are passed to this instance argument parser (by default
        :class:`configargparse.ArgumentParser`).
        See :func:`argparse.ArgumentParser.add_argument` for details on this
        functions arguments.

        The arguments are stored to recreate a parser with only some selected
        arguments later.
        """
        action = self.parser.add_argument(*args, **kwargs)
        self.parameters_args[action.dest] = (args, kwargs)
        self._actions[action.dest] = action

    @classmethod
    def new_parser(cls) -> argparse.ArgumentParser:
        """Return an instance of argument parser."""
        parser = configargparse.ArgumentParser(
            default_config_files=cls.DEFAULT_CONFIG_FILES
        )
        return parser

    def get_parser(
            self,
            select_params: Sequence[str] | None
    ) -> argparse.ArgumentParser:
        """Create a new parser for only some parameters.

        Parameters
        ----------
        select_params:
            Paremeters to parse for. If None, all registered parameters are
            selected.
        """
        if select_params is None:
            select_params = list(self.parameters_args.keys())

        parser = self.new_parser()

        for param in select_params:
            param_args, param_kwargs = self.parameters_args[param]
            parser.add_argument(*param_args, **param_kwargs)

        return parser

    def get_parameters(
            self,
            select_params: Sequence[str] | None = None,
            add_params: Callable[[argparse.ArgumentParser], None] | None = None,
            ignore_unknown_args: bool = False,
            ignore_command_line_args: bool = False,
            **values: Any) -> dict:
        """Get parameters from command line and config files.

        Parameters
        ----------
        select_params:
            Paremeters to parse for. If None, all registered parameters are
            selected.
        add_params:
            Function acting on the current parser that will be called after
            creating the parser. Can be used to add un-registered parameters.
        ignore_unknown_args:
            If True, will ignore unknown arguments. If False (default), an
            error will be raised if the command line contains unknown arguments.
        ignore_command_line_args:
            If True, will ignore command line arguments completely. Default
            is False.
        """
        self.last_parser = self.get_parser(select_params)

        # Override defaults
        self.last_parser.set_defaults(**values)
        # Callback
        if add_params is not None:
            add_params(self.last_parser)

        args: Sequence[str] | None = None
        if ignore_command_line_args:
            args = []

        params, _ = self.last_parser.parse_known_args(args)

        # Just to check if we have some unwanted arguments
        # We need to use the full parser because `last_parser` does not know
        # about all the parameters that can be present in config files
        if not ignore_unknown_args:
            self.parser.parse_args(args)

        return vars(params)

    def write_default_config(
            self,
            filename: PathLike
    ):
        """Write default values to a config file."""
        import textwrap
        if path.isfile(filename):
            raise ValueError(f"'{filename}' already exists.")

        with open(filename, 'w') as f:
            print('[parameters]', file=f)

            for action in self._actions.values():
                # check if at least one of the option string is --long-form
                if not any(arg.startswith(2*c)
                           for arg in action.option_strings
                           for c in self.parser.prefix_chars):
                    continue

                print(f'\n# {action.option_strings}', file=f)
                if action.help:
                    for line in textwrap.wrap(action.help):
                        print('# ' + line, file=f)
                print(f'{action.dest} = {action.default}', file=f)


params_manager = ParametersManager()

params_manager.register_parameter(
    '-r', '--region', type=str, default='GS',
    help='Name of the region to work in.'
)
params_manager.register_parameter(
    '-d', '--data', type=str, default='modis',
    help='Type of data to work on.'
)
params_manager.register_parameter(
    '--scale', action=argparse.BooleanOptionalAction, default=False,
    help='Size of the HI window in km.'
)

params_manager.write_default_config('./test_write.ini')

params = params_manager.get_parameters()
print(params)
